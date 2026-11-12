"""Compute all configured metrics for the he-en language pair.

he-en (WMT23) is absent from the RicardoRei/wmt-mqm-human-evaluation HF dataset
but the Google TSV spans are in wmt_mqm_span_dir. This script:
  1. Loads spans from the TSV and converts to sentence-level scores
     (one row per system × segment, segment_id = he_<system>_<globalSegId>).
  2. Runs all metrics configured in settings.toml on those rows.
  3. Appends the he rows to the existing per-metric score CSVs in results/.

After this script finishes, run --analysis-only to regenerate correlations including he.
"""

# SUPERSEDED 2026-11-09: this script used the pre-fix span loader conventions
# (default TSV quoting, <v> markup left in, one row per error, refA kept).
# Running it would overwrite the he/es block in results/scores_*.csv with
# wrong rows. Use scripts/rescore_span_block.py + scripts/splice_span_block.py.
import sys as _sys
if "--i-know-this-is-superseded" not in _sys.argv:
    _sys.exit(f"{__file__} is superseded; see the comment at the top of the file.")


import argparse
import gc
import logging
import sys
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mqmbench.config import init_settings, settings
from mqmbench.constants import AnnotationTier
from mqmbench.data.converter import annotations_to_sentence_scores
from mqmbench.data.utils import lang_from_pair
from mqmbench.data.wmt_mqm import build_sacrebleu_ref_lookup, load_wmt_mqm_spans


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", default="settings.toml")
    return parser.parse_args()


def _maybe_free_gpu():
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def main():
    args = parse_args()
    init_settings(args.settings)

    span_dir = Path(getattr(settings.data, "wmt_mqm_span_dir", ""))
    if not span_dir.exists():
        print(f"ERROR: wmt_mqm_span_dir not found: {span_dir}", file=sys.stderr)
        sys.exit(1)

    he_pairs = [lp for lp in settings.data.wmt_mqm_pairs if lang_from_pair(lp) == "he"]
    if not he_pairs:
        print("No he language pair in wmt_mqm_pairs — nothing to do.")
        return

    print("Loading he-en spans from TSV...", flush=True)
    # BUG FIX (found via advisor review, 2026-09-11): the Google MQM span TSVs do not
    # include reference text at all (see load_wmt_mqm_spans docstring) -- without
    # ref_lookups, every row's 'reference' column silently defaults to "". This script
    # previously called load_wmt_mqm_spans without ref_lookups, so every reference-based
    # metric scored here (confirmed: COMET-22, BLEURT) was scored against an empty
    # string instead of the real WMT23 reference, producing a compressed, near-random
    # score distribution that was misread as a genuine OOD-training-coverage effect.
    # Metrics scored via the main pipeline fallback (BLEU, BERTScore, xCOMET) were
    # unaffected since that path already builds ref_lookups correctly.
    ref_lookup = build_sacrebleu_ref_lookup("he-en", "wmt23", global_seg_id_offset=0)
    spans = load_wmt_mqm_spans(span_dir, lang_pairs=he_pairs, ref_lookups={"he": ref_lookup} if ref_lookup else None)
    if spans.empty:
        print("ERROR: no span data loaded for he-en", file=sys.stderr)
        sys.exit(1)

    he_df = annotations_to_sentence_scores(spans)
    he_df["annotation_tier"] = AnnotationTier.HUMAN_MQM
    print(f"  {len(he_df)} he segments (unique system×segment pairs)", flush=True)
    print(f"  quality_score variance: {he_df['quality_score'].std():.4f}", flush=True)

    sources = he_df["source"].tolist()
    hyps    = he_df["hypothesis"].tolist()
    refs    = he_df.get("reference", pd.Series([""] * len(he_df))).tolist()

    output_dir = Path(settings.data.results_dir)
    metrics_to_run = list(settings.metrics.run)
    print(f"  Metrics: {metrics_to_run}", flush=True)

    for metric in metrics_to_run:
        out_path = output_dir / f"scores_{metric}.csv"
        if not out_path.exists():
            print(f"  SKIP {metric}: no existing checkpoint at {out_path}", flush=True)
            continue

        existing = pd.read_csv(out_path)
        if "segment_id" in existing.columns and he_df["segment_id"].isin(existing["segment_id"]).any():
            print(f"  SKIP {metric}: he segment_ids already present in checkpoint", flush=True)
            continue

        print(f"  Computing {metric}...", flush=True)
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
            print(f"  SKIP {metric}: not handled in this script", flush=True)
            continue

        he_rows = he_df[["segment_id", "lang", "annotation_tier"]].copy()
        he_rows[metric] = score_col
        combined = pd.concat([existing, he_rows], ignore_index=True)
        combined.to_csv(out_path, index=False)
        print(f"  Appended {len(he_rows)} he rows to {out_path}", flush=True)

    print("\nDone. Now run: python scripts/run_pipeline.py --settings settings.toml --analysis-only",
          flush=True)


if __name__ == "__main__":
    main()
