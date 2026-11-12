"""Compute GEMBA-MQM scores for span-based MQM language pairs (he, es).

Appends new rows to results/scores_gemba.csv.
Skips languages already present unless --force is passed.
"""

# SUPERSEDED 2026-11-09: this script used the pre-fix span loader conventions
# (default TSV quoting, <v> markup left in, one row per error, refA kept).
# Running it would overwrite the he/es block in results/scores_*.csv with
# wrong rows. Use scripts/rescore_span_block.py + scripts/splice_span_block.py.
import sys as _sys
if "--i-know-this-is-superseded" not in _sys.argv:
    _sys.exit(f"{__file__} is superseded; see the comment at the top of the file.")


import argparse
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
    _REF_FILE_OVERRIDES,
    _SACREBLEU_OFFSETS,
    build_sacrebleu_ref_lookup,
    load_wmt_mqm_spans,
)

_WMT_YEAR = {"he-en": "wmt23", "en-es": "wmt24"}

_LANG_INFO = {
    "he": {"source_lang": "Hebrew",  "target_lang": "English"},
    "es": {"source_lang": "English", "target_lang": "Spanish"},
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--settings", default="settings.toml")
    p.add_argument("--force", action="store_true",
                   help="Re-score even if lang rows already present")
    return p.parse_args()


def main():
    args = parse_args()
    init_settings(args.settings)

    gemba_model = getattr(settings.metrics, "gemba_model", "")
    if not gemba_model:
        logger.error("gemba_model not set in settings.toml")
        sys.exit(1)

    span_dir = Path(getattr(settings.data, "wmt_mqm_span_dir", ""))
    if not span_dir.exists():
        logger.error(f"wmt_mqm_span_dir not found: {span_dir}")
        sys.exit(1)

    out_path = Path(settings.data.results_dir) / "scores_gemba.csv"
    existing = pd.read_csv(out_path) if out_path.exists() else pd.DataFrame()

    missing_pairs = [lp for lp in _WMT_YEAR if lp in getattr(settings.data, "wmt_mqm_pairs", [])]
    if not missing_pairs:
        # Fall back to both pairs if not explicitly configured
        missing_pairs = list(_WMT_YEAR.keys())

    # Build reference lookups (GEMBA is reference-free but span loader needs refs to populate the df)
    ref_lookups = {}
    for lp in missing_pairs:
        testset = _WMT_YEAR[lp]
        offset = _SACREBLEU_OFFSETS.get((testset, lp), 0)
        ref_override = _REF_FILE_OVERRIDES.get((testset, lp))
        lookup = build_sacrebleu_ref_lookup(
            lp, testset, global_seg_id_offset=offset, ref_file_override=ref_override
        )
        if lookup:
            lang_code = lang_from_pair(lp)
            ref_lookups[lang_code] = lookup

    spans = load_wmt_mqm_spans(span_dir, lang_pairs=missing_pairs,
                                ref_lookups=ref_lookups or None)
    if spans.empty:
        logger.error("No span data loaded.")
        sys.exit(1)

    from mqmbench.metrics import gemba

    new_rows_all = []
    for lang in spans["lang"].unique():
        already_present = (
            not existing.empty
            and "lang" in existing.columns
            and (existing["lang"] == lang).any()
        )
        if already_present and not args.force:
            logger.info(f"  SKIP {lang}: already in scores_gemba.csv")
            continue

        if already_present and args.force:
            existing = existing[existing["lang"] != lang].reset_index(drop=True)
            logger.info(f"  Removed existing {lang} rows (--force)")

        sub = spans[spans["lang"] == lang]
        df = annotations_to_sentence_scores(sub)
        df["annotation_tier"] = AnnotationTier.HUMAN_MQM

        info = _LANG_INFO.get(lang, {})
        cache_file = str(Path(settings.data.results_dir) / f"gemba_cache_{lang}.jsonl")

        logger.info(f"  Scoring GEMBA for {lang} ({len(df)} segments)...")
        scores = gemba.score(
            sources=df["source"].tolist(),
            hypotheses=df["hypothesis"].tolist(),
            references=df.get("reference", pd.Series([""] * len(df))).tolist(),
            lang=info.get("target_lang", lang),
            model_name=gemba_model,
            source_lang=info.get("source_lang", "English"),
            target_lang=info.get("target_lang", lang),
            batch_size=getattr(settings.metrics, "gemba_batch_size", 32),
            cache_file=cache_file,
        )

        new_rows = df[["segment_id", "lang", "annotation_tier"]].copy()
        new_rows["gemba"] = scores
        new_rows_all.append(new_rows)
        logger.info(f"    {lang}: {len(new_rows)} rows scored")

    if new_rows_all:
        combined = pd.concat([existing] + new_rows_all, ignore_index=True)
        combined.to_csv(out_path, index=False)
        logger.info(f"Saved {out_path} ({len(combined)} total rows)")
    else:
        logger.info("Nothing to score.")


if __name__ == "__main__":
    main()
