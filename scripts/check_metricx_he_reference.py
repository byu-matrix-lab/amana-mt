"""One-off diagnostic (advisor review, 2026-09-11): does scores_metricx.csv's
Hebrew checkpoint match a correct-reference or empty-reference recomputation?

Same class of check as check_xcomet_he_reference.py -- MetricX-24 is
reference-based, so it's a candidate for the same empty-reference bug that
hit COMET-22, BLEURT, and xCOMET.

Run from project root via scripts/slurm/run_check_metricx_he.sh
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mqmbench.config import init_settings, settings
from mqmbench.data.wmt_mqm import build_sacrebleu_ref_lookup, load_wmt_mqm_spans
from mqmbench.data.converter import annotations_to_sentence_scores


def main():
    init_settings("settings.toml")
    span_dir = Path(settings.data.wmt_mqm_span_dir)

    lookup = build_sacrebleu_ref_lookup("he-en", "wmt23", global_seg_id_offset=0)
    spans = load_wmt_mqm_spans(span_dir, lang_pairs=["he-en"], ref_lookups={"he": lookup})
    he_df = annotations_to_sentence_scores(spans).drop_duplicates("segment_id").reset_index(drop=True)
    print(f"unique he rows: {len(he_df)}", flush=True)

    ckpt = pd.read_csv("results/scores_metricx.csv")
    ckpt_he = ckpt[ckpt.lang == "he"].drop_duplicates("segment_id")
    print(f"checkpoint unique he rows: {len(ckpt_he)}", flush=True)

    from mqmbench.metrics import metricx as metricx_metric
    sources = he_df["source"].tolist()
    hyps = he_df["hypothesis"].tolist()
    refs = he_df["reference"].tolist()

    print("Scoring with correct reference...", flush=True)
    correct_scores = metricx_metric.score(sources, hyps, refs, batch_size=32)
    print("Scoring with empty reference...", flush=True)
    empty_scores = metricx_metric.score(sources, hyps, [""] * len(he_df), batch_size=32)

    he_df = he_df.copy()
    he_df["mx_correct"] = correct_scores
    he_df["mx_empty"] = empty_scores
    merged = he_df[["segment_id", "mx_correct", "mx_empty"]].merge(
        ckpt_he[["segment_id", "metricx"]], on="segment_id", how="inner"
    )
    print(f"merged rows: {len(merged)}", flush=True)
    print(merged[["mx_correct", "mx_empty", "metricx"]].describe(), flush=True)
    print("corr checkpoint vs correct-ref:", np.corrcoef(merged["metricx"], merged["mx_correct"])[0, 1], flush=True)
    print("corr checkpoint vs empty-ref:  ", np.corrcoef(merged["metricx"], merged["mx_empty"])[0, 1], flush=True)
    merged.to_csv("/tmp/metricx_he_full_check.csv", index=False)


if __name__ == "__main__":
    main()
