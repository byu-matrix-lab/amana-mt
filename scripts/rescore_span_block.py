"""Rebuild and rescore the he-en / en-es span-fallback block (2026-11-09).

The block is the last part of every results/scores_<metric>.csv (after the HF
MQM, DA and Tier-2 rows). The label fixes in mqmbench.data.wmt_mqm (quote-safe
parsing, <v> markup stripped, one row per (system, segment), no canary/refA,
correct en-es reference line) change its rows, so every metric is recomputed
for it here with the pipeline's own _run_metrics. GEMBA is not rerun (he/es
GEMBA is excluded from the paper); scripts/splice_span_block.py fills NaN.

Output: results/span_block_2026-11-09/{block.parquet, scores_<metric>.csv}
Run on a GPU node:  sbatch scripts/slurm/run_rescore_span_block.sh
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mqmbench.config import init_settings, settings  # noqa: E402
from mqmbench.data.wmt_mqm import load_span_fallback_scores  # noqa: E402
from mqmbench.pipeline import _run_metrics  # noqa: E402

OUT = ROOT / "results" / "span_block_2026-11-09"


def main():
    init_settings(str(ROOT / "settings.toml"))
    OUT.mkdir(parents=True, exist_ok=True)
    block = load_span_fallback_scores(settings.data.wmt_mqm_span_dir, ["he-en", "en-es"])
    print(block.groupby("lang").size().to_dict(), flush=True)
    block.to_parquet(OUT / "block.parquet")
    metrics = [m for m in settings.metrics.run if m != "gemba"]
    print("metrics:", metrics, flush=True)
    _run_metrics(block, settings, checkpoint_dir=OUT, only_metrics=metrics)
    for m in metrics:
        assert block[m].notna().all(), f"{m} has NaN"
    print("done", flush=True)


if __name__ == "__main__":
    main()
