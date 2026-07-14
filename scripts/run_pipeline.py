#!/usr/bin/env python3
"""CLI entry point for the multilingual MQM benchmark pipeline.

Usage:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --settings path/to/settings.toml
    python scripts/run_pipeline.py --only-metrics xcomet  # single metric per job
    python scripts/run_pipeline.py --analysis-only        # skip metrics, run analysis
"""

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mqmbench.pipeline import run_pipeline


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate MT metrics against human MQM annotations."
    )
    parser.add_argument(
        "--settings",
        default="settings.toml",
        help="Path to settings TOML file (default: settings.toml)",
    )
    parser.add_argument(
        "--only-metrics",
        nargs="+",
        metavar="METRIC",
        help="Override metrics.run — compute only these metrics (e.g. --only-metrics xcomet). "
             "Use a dependency chain of SLURM jobs to run one metric per process and avoid "
             "MaxRSS accumulation across sequentially loaded large models.",
    )
    parser.add_argument(
        "--analysis-only",
        action="store_true",
        help="Skip all metric computation; load checkpoint and run correlation analysis only.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    settings_path = Path(args.settings).resolve()
    if not settings_path.exists():
        print(f"Error: settings file not found: {settings_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Using settings: {settings_path}", flush=True)
    results = run_pipeline(
        str(settings_path),
        only_metrics=args.only_metrics,
        analysis_only=args.analysis_only,
    )

    if results is not None:
        print("\n=== Correlation Summary by Resource Tier ===")
        print(results["tier_summary"].to_string(index=False))
        print("\n=== Per-Language Results ===")
        print(results["correlations"].to_string(index=False))


if __name__ == "__main__":
    main()
