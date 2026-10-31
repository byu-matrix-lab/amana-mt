"""One-off diagnostic (advisor review, 2026-09-11): does scores_xcomet.csv's
Hebrew checkpoint match a correct-reference or empty-reference recomputation?

compute_span_scores.py (which computes xcomet for he-en) correctly builds
ref_lookups, so this should come back clean -- but an initial small-sample
(n=60) CPU test suggested otherwise (checkpoint correlated more with the
empty-reference recompute than the correct one). This reruns that test at
a larger sample size on GPU to settle it definitively.

Run from project root via scripts/slurm/run_check_xcomet_he.sh
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

    ckpt = pd.read_csv("results/scores_xcomet.csv")
    ckpt_he = ckpt[ckpt.lang == "he"].drop_duplicates("segment_id")
    print(f"checkpoint unique he rows: {len(ckpt_he)}", flush=True)

    from mqmbench.metrics import comet
    sources = he_df["source"].tolist()
    hyps = he_df["hypothesis"].tolist()
    refs = he_df["reference"].tolist()

    print("Scoring with correct reference...", flush=True)
    correct_scores = comet.score_xcomet(sources, hyps, refs, batch_size=32, gpus=1)
    print("Scoring with empty reference...", flush=True)
    empty_scores = comet.score_xcomet(sources, hyps, [""] * len(he_df), batch_size=32, gpus=1)

    he_df = he_df.copy()
    he_df["xc_correct"] = correct_scores
    he_df["xc_empty"] = empty_scores
    merged = he_df[["segment_id", "xc_correct", "xc_empty"]].merge(
        ckpt_he[["segment_id", "xcomet"]], on="segment_id", how="inner"
    )
    print(f"merged rows: {len(merged)}", flush=True)
    print(merged[["xc_correct", "xc_empty", "xcomet"]].describe(), flush=True)
    print("corr checkpoint vs correct-ref:", np.corrcoef(merged["xcomet"], merged["xc_correct"])[0, 1], flush=True)
    print("corr checkpoint vs empty-ref:  ", np.corrcoef(merged["xcomet"], merged["xc_empty"])[0, 1], flush=True)
    merged.to_csv("/tmp/xcomet_he_full_check.csv", index=False)


if __name__ == "__main__":
    main()
