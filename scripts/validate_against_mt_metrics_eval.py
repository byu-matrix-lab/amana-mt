"""Segment-level external validation against the official mt-metrics-eval-v2
per-system, per-segment score releases for the two span-fallback language
pairs (he-en/wmt23, en-es/wmt24).

Why segment-level and not system-level: aggregating our recomputed scores to
one mean per system and correlating those ~12-14 system means against the
official system means is a weak check -- it is forgiving of underlying
per-segment misalignment because averaging cancels noise. Advisor review
(2026-09-12) flagged the paper's earlier system-level validation (Pearson/
Spearman >= ~0.81-0.98) as too loose a claim; this script instead pairs our
own per-(system, segment) score with the official per-(system, segment)
score directly and correlates the full paired vectors (~8,700-8,900 points
per metric), which is sensitive to exactly the kind of segment
misalignment/reference bug this project has twice found and fixed this
session (Hebrew's segment_id collision, Spanish's multi-domain globalSegId
reuse).

Uses the per-segment score files from the mt-metrics-eval-v2 data release
(https://github.com/google/mt-metrics-eval), vendored under
results/external_refs/mt-metrics-eval-v2/ for exactly the two (testset, lang
pair) combinations this project needs -- see results/external_refs/README.md.
"""
import sys
from pathlib import Path

import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
MTME = ROOT / "results" / "external_refs" / "mt-metrics-eval-v2"

SPECS = [
    dict(lang="he", testset="wmt23", lp="he-en", offset=0,
         metrics={"comet": "COMET-refA", "bleurt": "BLEURT-20-refA",
                   "xcomet": "XCOMET-Ensemble-refA", "metricx": "MetricX-23-refA"}),
    dict(lang="es", testset="wmt24", lp="en-es", offset=-1,
         metrics={"comet": "COMET-22-refA", "bleurt": "BLEURT-20-refA",
                   "xcomet": "XCOMET-refA", "metricx": "MetricX-24-refA"}),
]

# Our own model checkpoints, for the paper's checkpoint-mismatch disclosure.
OUR_CHECKPOINTS = {
    "comet": "Unbabel/wmt22-comet-da",
    "bleurt": "Elron/bleurt-large-512",  # unofficial HF port, NOT Google's official BLEURT-20 checkpoint
    "xcomet": "Unbabel/XCOMET-XL",
    "metricx": "google/metricx-24-hybrid-large-v2p6-bfloat16",  # MetricX-24 for BOTH langs
}


def main() -> None:
    if not MTME.exists():
        sys.exit(f"mt-metrics-eval-v2 data not found at {MTME} -- see script docstring")

    rows = []
    for spec in SPECS:
        lang, testset, lp, offset = spec["lang"], spec["testset"], spec["lp"], spec["offset"]
        for our_metric, official_name in spec["metrics"].items():
            ckpt = pd.read_csv(ROOT / "results" / f"scores_{our_metric}.csv")
            ckpt_lang = ckpt[ckpt.lang == lang].copy()
            # segment_id format: "{lang}_{system}_{globalSegId}_{rater_idx}"
            # (multiple MQM raters can score the same system/segment; the
            # metric score itself doesn't depend on rater, so dedupe).
            parts = ckpt_lang["segment_id"].str.split("_")
            ckpt_lang["system"] = parts.apply(lambda p: "_".join(p[1:-2]))
            ckpt_lang["global_seg_id"] = parts.str[-2].astype(int)
            ours = ckpt_lang.drop_duplicates(subset=["system", "global_seg_id"])[
                ["system", "global_seg_id", our_metric]
            ].rename(columns={our_metric: "our_score"})

            path = MTME / testset / "metric-scores" / lp / f"{official_name}.seg.score"
            official = pd.read_csv(path, sep="\t", header=None, names=["system", "score"])
            official["line_idx"] = official.groupby("system").cumcount()
            official["global_seg_id"] = official["line_idx"] + (-offset)

            merged = official.merge(ours, on=["system", "global_seg_id"], how="inner")
            merged = merged.dropna(subset=["score", "our_score"])
            n = len(merged)
            pear = stats.pearsonr(merged.score, merged.our_score)[0] if n > 2 else float("nan")
            spear = stats.spearmanr(merged.score, merged.our_score)[0] if n > 2 else float("nan")
            same_checkpoint = official_name.split("-refA")[0].replace("-Ensemble", "") in OUR_CHECKPOINTS[our_metric]
            rows.append(dict(
                lang=lang, testset=testset, metric=our_metric,
                official_metric_name=official_name, our_checkpoint=OUR_CHECKPOINTS[our_metric],
                n_segments=n, n_systems=merged.system.nunique(),
                pearson_r=round(float(pear), 4), spearman_r=round(float(spear), 4),
                source=f"mt-metrics-eval-v2/{testset}/metric-scores/{lp}/{official_name}.seg.score",
            ))
            print(f"{lang} {our_metric}: n={n} systems={merged.system.nunique()} "
                  f"pearson={pear:.4f} spearman={spear:.4f}")

    out = pd.DataFrame(rows)
    out_path = ROOT / "results" / "wmt_baseline_validation_segment_level.csv"
    out.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
