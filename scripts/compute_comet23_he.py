"""Score Hebrew segments with an additional reference-based model and compare to COMET-22.

NOTE: Unbabel/wmt23-comet-da does not exist as a public model. The nearest
available comparison is Unbabel/XCOMET-XL (already run in the main pipeline).
This script is retained for provenance; the xCOMET vs COMET-22 Hebrew
comparison is summarised in analyze_abjad_mechanism.py.

For the OOD mechanism validation, see:
  - scripts/analyze_abjad_mechanism.py (Hebrew vs Pashto contrast — clean test)
  - results/abjad_metric_comparison.csv
"""

import gc
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mqmbench.config import init_settings, settings
from mqmbench.constants import AnnotationTier
from mqmbench.data.converter import annotations_to_sentence_scores
from mqmbench.data.utils import lang_from_pair
from mqmbench.data.wmt_mqm import load_wmt_mqm_spans

COMET23_MODEL = "Unbabel/wmt23-comet-da"
COMET22_MODEL = "Unbabel/wmt22-comet-da"


def cohen_d_quartile(scores: pd.Series) -> float:
    q1, q3 = scores.quantile(0.25), scores.quantile(0.75)
    bot, top = scores[scores <= q1], scores[scores >= q3]
    if len(bot) < 2 or len(top) < 2:
        return float("nan")
    pooled_sd = np.sqrt((bot.var() + top.var()) / 2)
    return float((top.mean() - bot.mean()) / pooled_sd) if pooled_sd > 0 else float("nan")


def print_compression_stats(label: str, scores: pd.Series, cross_mean: float, cross_std: float):
    z = (scores.mean() - cross_mean) / cross_std
    d = cohen_d_quartile(scores)
    print(f"  {label}:")
    print(f"    mean={scores.mean():.4f}  std={scores.std():.4f}  "
          f"z={z:.2f}σ  Cohen_d(IQR)={d:.2f}  n={len(scores)}")


def main():
    project_root = Path(__file__).resolve().parent.parent
    init_settings(str(project_root / "settings.toml"))

    span_dir = Path(getattr(settings.data, "wmt_mqm_span_dir", ""))
    if not span_dir.exists():
        print(f"ERROR: wmt_mqm_span_dir not found: {span_dir}", file=sys.stderr)
        sys.exit(1)

    results_dir = Path(settings.data.results_dir)
    out_path = results_dir / "scores_comet23.csv"

    # ------------------------------------------------------------------ #
    # 1.  Load Hebrew segments                                             #
    # ------------------------------------------------------------------ #
    he_pairs = [lp for lp in settings.data.wmt_mqm_pairs if lang_from_pair(lp) == "he"]
    if not he_pairs:
        print("No he pair in wmt_mqm_pairs — nothing to do.")
        return

    print("Loading he-en spans from TSV...", flush=True)
    spans = load_wmt_mqm_spans(span_dir, lang_pairs=he_pairs)
    if spans.empty:
        print("ERROR: no span data for he-en", file=sys.stderr)
        sys.exit(1)

    he_df = annotations_to_sentence_scores(spans)
    he_df["annotation_tier"] = AnnotationTier.HUMAN_MQM
    print(f"  {len(he_df)} Hebrew segments (system × segment pairs)", flush=True)

    sources = he_df["source"].tolist()
    hyps    = he_df["hypothesis"].tolist()
    refs    = he_df.get("reference", pd.Series([""] * len(he_df))).tolist()

    # ------------------------------------------------------------------ #
    # 2.  Check if already scored                                          #
    # ------------------------------------------------------------------ #
    if out_path.exists():
        existing = pd.read_csv(out_path)
        if he_df["segment_id"].isin(existing["segment_id"]).all():
            print(f"  SKIP: all Hebrew segments already in {out_path}", flush=True)
        else:
            print(f"  Partial results found; will append missing segments.", flush=True)
            already = set(existing["segment_id"])
            mask = ~he_df["segment_id"].isin(already)
            he_df = he_df[mask]
            sources = he_df["source"].tolist()
            hyps    = he_df["hypothesis"].tolist()
            refs    = he_df.get("reference", pd.Series([""] * len(he_df))).tolist()

    # ------------------------------------------------------------------ #
    # 3.  Score with COMET-23                                              #
    # ------------------------------------------------------------------ #
    if len(he_df) > 0:
        print(f"  Scoring {len(he_df)} segments with {COMET23_MODEL}...", flush=True)
        from mqmbench.metrics import comet as comet_metric
        scores23 = comet_metric.score(
            sources, hyps, refs,
            model_name=COMET23_MODEL,
            batch_size=getattr(settings.metrics.comet, "batch_size", 16),
            gpus=getattr(settings.metrics.comet, "gpus", 1),
        )
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        new_rows = he_df[["segment_id", "lang", "annotation_tier"]].copy()
        new_rows["comet23"] = scores23

        if out_path.exists():
            existing = pd.read_csv(out_path)
            combined = pd.concat([existing, new_rows], ignore_index=True)
        else:
            combined = new_rows
        combined.to_csv(out_path, index=False)
        print(f"  Saved {len(new_rows)} rows to {out_path}", flush=True)

    # ------------------------------------------------------------------ #
    # 4.  Score compression comparison: COMET-22 vs COMET-23              #
    # ------------------------------------------------------------------ #
    print("\n" + "=" * 60)
    print("Score Compression Analysis: COMET-22 vs COMET-23 on Hebrew")
    print("=" * 60)

    comet22_path = results_dir / "scores_comet.csv"
    if not comet22_path.exists():
        print("  No scores_comet.csv found; skipping comparison.", flush=True)
        return

    c22_all = pd.read_csv(comet22_path)
    c23_all = pd.read_csv(out_path)

    # Cross-language reference from COMET-22 (excluding Hebrew)
    cross = c22_all[c22_all["lang"] != "he"]["comet"].dropna()
    cross_mean, cross_std = cross.mean(), cross.std()
    print(f"\nCross-language COMET-22 reference (excluding Hebrew):")
    print(f"  mean={cross_mean:.4f}  std={cross_std:.4f}")

    c22_he = c22_all[c22_all["lang"] == "he"]["comet"].dropna()
    c23_he = c23_all[c23_all["lang"] == "he"]["comet23"].dropna()

    print(f"\nHebrew:")
    if len(c22_he) > 0:
        print_compression_stats("COMET-22 (wmt22-comet-da)", c22_he, cross_mean, cross_std)
    if len(c23_he) > 0:
        # cross-language reference for COMET-23 would ideally use COMET-23 scores for other langs;
        # use COMET-22 as approximate reference (similar scale)
        print_compression_stats("COMET-23 (wmt23-comet-da)", c23_he, cross_mean, cross_std)

    if len(c22_he) > 0 and len(c23_he) > 0:
        mean_shift = c23_he.mean() - c22_he.mean()
        d22 = cohen_d_quartile(c22_he)
        d23 = cohen_d_quartile(c23_he)
        print(f"\n  Mean shift (COMET-23 − COMET-22): {mean_shift:+.4f}")
        print(f"  Cohen's d shift: {d22:.2f} → {d23:.2f}")
        if mean_shift > 0.05 and d23 > d22:
            print("\n  RESULT: COMET-23 shows reduced score compression on Hebrew.")
            print("  This is consistent with the OOD training-data mechanism:")
            print("  COMET-23 includes Hebrew in its training distribution.")
        elif abs(mean_shift) < 0.02:
            print("\n  RESULT: COMET-23 and COMET-22 show similar compression.")
            print("  The compression may not be purely OOD-driven — investigate further.")
        else:
            print(f"\n  RESULT: Shift={mean_shift:+.4f} — review manually.")

    print(f"\nDone. Full scores in {out_path}")


if __name__ == "__main__":
    main()
