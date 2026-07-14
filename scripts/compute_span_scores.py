"""Compute metrics for span-based MQM language pairs missing from the HF dataset.

Handles he-en (WMT23) and en-es (WMT24). Fetches reference translations from
the local sacreBLEU cache so that reference-based metrics (BLEU, ChrF, BLEURT,
BERTScore) score correctly.

For each metric and language:
- If lang rows are ABSENT from the score CSV: compute and append.
- If lang rows are PRESENT but reference-based metrics scored them against empty
  strings (resulting in all-zero scores): delete stale rows and recompute.
- Otherwise: skip.

Run after deleting stale rows manually if needed, or let --force re-score.
"""

import argparse
import gc
import logging
import sys
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mqmbench.config import init_settings, settings
from mqmbench.constants import AnnotationTier
from mqmbench.data.converter import annotations_to_sentence_scores
from mqmbench.data.utils import lang_from_pair
from mqmbench.data.wmt_mqm import (
    _SACREBLEU_OFFSETS,
    build_sacrebleu_ref_lookup,
    load_wmt_mqm_spans,
)

# Reference-based metrics that need real references to produce meaningful scores
REFERENCE_BASED = {"bleu", "chrf", "bleurt", "bertscore"}

# WMT year for each lang pair we handle
_WMT_YEAR = {"he-en": "wmt23", "en-es": "wmt24"}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--settings", default="settings.toml")
    p.add_argument("--force", action="store_true",
                   help="Re-score even if segment_ids already present (overwrites stale zeros)")
    p.add_argument("--langs", nargs="*",
                   help="Only process these langs (e.g. --langs he es). Default: all missing pairs")
    return p.parse_args()


def _maybe_free_gpu():
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _is_all_zero(series: pd.Series) -> bool:
    """True if all non-NaN values are 0 (stale empty-ref scores)."""
    valid = series.dropna()
    return len(valid) > 0 and (valid == 0).all()


def main():
    args = parse_args()
    init_settings(args.settings)

    span_dir = Path(getattr(settings.data, "wmt_mqm_span_dir", ""))
    if not span_dir.exists():
        logger.error(f"wmt_mqm_span_dir not found: {span_dir}")
        sys.exit(1)

    hf_langs = set()  # langs already covered by the HF dataset
    try:
        from datasets import load_dataset
        hf_df = load_dataset("RicardoRei/wmt-mqm-human-evaluation", split="train").to_pandas()
        from mqmbench.data.wmt_mqm import load_wmt_mqm
        hf_langs = {lang_from_pair(lp) for lp in hf_df["lp"].unique()}
    except Exception:
        pass  # offline — assume we need to compute everything

    # Determine which pairs to process
    all_pairs = list(settings.data.wmt_mqm_pairs)
    missing_pairs = [lp for lp in all_pairs
                     if lang_from_pair(lp) not in hf_langs and lp in _WMT_YEAR]
    if args.langs:
        missing_pairs = [lp for lp in missing_pairs if lang_from_pair(lp) in args.langs]
    if not missing_pairs:
        logger.info("No span-based lang pairs to process.")
        return

    logger.info(f"Processing pairs: {missing_pairs}")

    # Build sacreBLEU reference lookups (requires cached sacreBLEU data)
    ref_lookups: dict[str, dict[int, str]] = {}
    for lp in missing_pairs:
        testset = _WMT_YEAR[lp]
        offset = _SACREBLEU_OFFSETS.get((testset, lp), 0)
        lookup = build_sacrebleu_ref_lookup(lp, testset, global_seg_id_offset=offset)
        if lookup:
            lang_code = lang_from_pair(lp)
            ref_lookups[lang_code] = lookup
            logger.info(f"  Ref lookup for {lp}: {len(lookup)} entries")
        else:
            logger.warning(f"  No ref lookup for {lp} — reference-based metrics will use empty refs")

    # Load spans with references
    spans = load_wmt_mqm_spans(span_dir, lang_pairs=missing_pairs,
                                ref_lookups=ref_lookups or None)
    if spans.empty:
        logger.error("No span data loaded.")
        sys.exit(1)

    lang_dfs: dict[str, pd.DataFrame] = {}
    for lang in spans["lang"].unique():
        sub = spans[spans["lang"] == lang]
        df = annotations_to_sentence_scores(sub)
        df["annotation_tier"] = AnnotationTier.HUMAN_MQM
        ref_filled = (df.get("reference", pd.Series(dtype=str)).str.len() > 0).sum()
        logger.info(f"  {lang}: {len(df)} segments, {ref_filled}/{len(df)} have reference")
        lang_dfs[lang] = df

    output_dir = Path(settings.data.results_dir)
    metrics_to_run = list(settings.metrics.run)

    for metric in metrics_to_run:
        out_path = output_dir / f"scores_{metric}.csv"
        if not out_path.exists():
            logger.info(f"  SKIP {metric}: no existing checkpoint at {out_path}")
            continue

        existing = pd.read_csv(out_path)
        is_ref_based = metric in REFERENCE_BASED

        # Determine which langs need scoring
        langs_to_score: list[str] = []
        for lang, df in lang_dfs.items():
            present = ("segment_id" in existing.columns and
                       df["segment_id"].isin(existing["segment_id"]).any())
            if not present:
                langs_to_score.append(lang)
            elif args.force or (is_ref_based and _is_all_zero(
                    existing.loc[existing["segment_id"].isin(df["segment_id"]), metric])):
                # Remove stale rows and recompute
                mask = existing["segment_id"].isin(df["segment_id"])
                n_removed = mask.sum()
                existing = existing[~mask].reset_index(drop=True)
                logger.info(f"  Removed {n_removed} stale {lang} rows from {metric} (all-zero ref-based scores)")
                langs_to_score.append(lang)
            else:
                logger.info(f"  SKIP {metric}/{lang}: already present")

        if not langs_to_score:
            continue

        logger.info(f"  Computing {metric} for {langs_to_score}...")
        all_new_rows = []

        for lang in langs_to_score:
            df = lang_dfs[lang]
            sources = df["source"].tolist()
            hyps = df["hypothesis"].tolist()
            refs = df.get("reference", pd.Series([""] * len(df))).tolist()

            score_col = None

            if metric == "bleu":
                from mqmbench.metrics import bleu
                score_col = bleu.score(sources, hyps, refs)

            elif metric == "chrf":
                from mqmbench.metrics import chrf
                score_col = chrf.score(sources, hyps, refs)

            elif metric == "bleurt":
                from mqmbench.metrics import bleurt as bleurt_metric
                score_col = bleurt_metric.score(
                    hyps, refs,
                    model_name=settings.metrics.bleurt.model,
                    batch_size=settings.metrics.bleurt.batch_size,
                )
                _maybe_free_gpu()

            elif metric == "bertscore":
                from mqmbench.metrics import bertscore
                score_col = bertscore.score(
                    sources, hyps, refs,
                    model_type=settings.metrics.bertscore.model,
                    batch_size=settings.metrics.bertscore.batch_size,
                )
                _maybe_free_gpu()

            elif metric == "comet":
                from mqmbench.metrics import comet
                score_col = comet.score(
                    sources, hyps, refs,
                    model_name=settings.metrics.comet.model,
                    batch_size=settings.metrics.comet.batch_size,
                    gpus=settings.metrics.comet.gpus,
                )
                _maybe_free_gpu()

            elif metric == "xcomet":
                from mqmbench.metrics import comet
                score_col = comet.score_xcomet(
                    sources, hyps, refs,
                    model_name=settings.metrics.xcomet.model,
                    batch_size=settings.metrics.xcomet.batch_size,
                    gpus=settings.metrics.xcomet.gpus,
                )
                _maybe_free_gpu()

            elif metric == "cometkiwi":
                from mqmbench.metrics import comet
                score_col = comet.score_kiwi(
                    sources, hyps,
                    model_name=settings.metrics.cometkiwi.model,
                    batch_size=settings.metrics.cometkiwi.batch_size,
                    gpus=settings.metrics.cometkiwi.gpus,
                )
                _maybe_free_gpu()

            elif metric == "cometkiwi23":
                from mqmbench.metrics import comet
                score_col = comet.score_kiwi(
                    sources, hyps,
                    model_name=settings.metrics.cometkiwi23.model,
                    batch_size=settings.metrics.cometkiwi23.batch_size,
                    gpus=settings.metrics.cometkiwi23.gpus,
                )
                _maybe_free_gpu()

            elif metric == "metricx":
                from mqmbench.metrics import metricx as metricx_metric
                score_col = metricx_metric.score(
                    sources, hyps, refs,
                    model_name=settings.metrics.metricx.model,
                    batch_size=settings.metrics.metricx.batch_size,
                )
                _maybe_free_gpu()

            else:
                logger.info(f"  SKIP {metric}/{lang}: not handled in this script")
                continue

            if score_col is not None:
                new_rows = df[["segment_id", "lang", "annotation_tier"]].copy()
                new_rows[metric] = score_col
                all_new_rows.append(new_rows)
                logger.info(f"    Scored {len(new_rows)} {lang} rows for {metric}")

        if all_new_rows:
            combined = pd.concat([existing] + all_new_rows, ignore_index=True)
            combined.to_csv(out_path, index=False)
            logger.info(f"  Saved {out_path} ({len(combined)} total rows)")

    logger.info("\nDone. Submit run_analysis_only.sh to regenerate correlations.")


if __name__ == "__main__":
    main()
