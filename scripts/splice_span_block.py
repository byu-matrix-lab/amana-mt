"""Splice the rebuilt he/es span block and the fixed MetricX scores into results/ (2026-11-09).

Every results/scores_<metric>.csv is [HF MQM | DA | Tier 2 | he/es span block],
aligned positionally with the pipeline's loader. This script:
  * keeps the prefix (all non-he/es rows) unchanged, except MetricX, whose
    prefix comes from results_metricx_fix/ (EOS fix; the chrF written next to
    it matched results/scores_chrf.csv row by row on every non-es row);
  * replaces the he/es suffix with results/span_block_2026-11-09/ (GEMBA: NaN,
    he/es GEMBA is excluded from the paper);
  * backs up every file it overwrites to results/backup_pre_label_fix_2026-11-09/.
Refuses to write if any alignment check fails.
"""
import hashlib
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
BLOCK = RES / "span_block_2026-11-09"
FIX = ROOT / "results_metricx_fix"
BACKUP = RES / "backup_pre_label_fix_2026-11-09"
METRICS = ["bleu", "chrf", "bleurt", "bertscore", "comet", "xcomet",
           "cometkiwi", "cometkiwi23", "metricx", "gemba"]
KEYS = ["segment_id", "lang", "annotation_tier"]


def fail(msg):
    sys.exit(f"REFUSING TO WRITE: {msg}")


def split(df, name):
    idx = np.flatnonzero(df["lang"].isin(["he", "es"]).values)
    if len(idx) == 0 or idx.min() != len(df) - len(idx) or not (np.diff(idx) == 1).all():
        fail(f"{name}: he/es rows are not a contiguous suffix")
    return df.iloc[: idx.min()].reset_index(drop=True)


def main():
    block = pd.read_parquet(BLOCK / "block.parquet")
    BACKUP.mkdir(exist_ok=True)
    ref_prefix = None
    out = {}
    for m in METRICS:
        old = pd.read_csv(RES / f"scores_{m}.csv")
        prefix = split(old, m)
        if ref_prefix is None:
            ref_prefix = prefix[KEYS]
        elif not (prefix[KEYS].values == ref_prefix.values).all():
            fail(f"{m}: prefix keys differ from scores_{METRICS[0]}.csv")
        if m == "metricx":
            fx = split(pd.read_csv(FIX / "scores_metricx.csv"), "fix/metricx")
            fc = split(pd.read_csv(FIX / "scores_chrf.csv"), "fix/chrf")
            oc = split(pd.read_csv(RES / "scores_chrf.csv"), "chrf")
            if len(fx) != len(prefix) or not (fx[["lang", "annotation_tier"]].values
                                              == prefix[["lang", "annotation_tier"]].values).all():
                fail("metricx fix prefix not aligned (lang/tier)")
            if not np.allclose(fc["chrf"].values, oc["chrf"].values, atol=1e-9):
                fail("metricx fix run's chrF does not match results/ chrF on the prefix")
            prefix = prefix.assign(metricx=fx["metricx"].values)
        if m == "gemba":
            suffix = block[KEYS].assign(gemba=np.nan)
        else:
            s = pd.read_csv(BLOCK / f"scores_{m}.csv")
            if not (s[KEYS].values == block[KEYS].values).all():
                fail(f"{m}: block scores not aligned with block.parquet")
            if s[m].isna().any():
                fail(f"{m}: NaN in block scores")
            suffix = s[KEYS + [m]]
        out[m] = pd.concat([prefix[KEYS + [m]], suffix], ignore_index=True)

    for m, df in out.items():
        src = RES / f"scores_{m}.csv"
        dst = BACKUP / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
        df.to_csv(src, index=False)
        h = hashlib.sha256(src.read_bytes()).hexdigest()[:12]
        print(f"wrote {src.name}: {len(df)} rows ({len(df) - len(block)} prefix + {len(block)} he/es) sha256 {h}")


if __name__ == "__main__":
    main()
