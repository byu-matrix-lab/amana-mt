"""MQM control: is the en->X > X->en gap in metric-human correlation a property
of the metrics, or of the human labels?

WMT20-22 have BOTH expert MQM and WMT DA on the same segments for zh-en
(X->en) and en-de / en-ru (en->X). On the identical (system, segment) set we
compute metric-human Spearman under each label type, plus metric-metric
agreement. Reads official mt-metrics-eval-v2 files only (no mqmbench code).

  If the direction gap appears under DA but not under MQM -> label artifact.
  If it persists under MQM too                           -> real metric effect.

Usage: python mqm_control.py <path to mt-metrics-eval-v2>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

MTME = Path(sys.argv[1])
ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mtme_io import LABELS, METRICS, PAIRS, load_pair  # noqa: E402


rows, agree_rows = [], []
for tset, lps in PAIRS.items():
    for lp in lps:
        df, da_protocol = load_pair(MTME, tset, lp)
        labels = [l for l in LABELS[tset] if l in df]
        metrics = [m for m in METRICS[tset] if m in df]
        # core comparison: MQM vs crowd DA on the identical segment set
        has_da = "DA" in df
        core = df.dropna(subset=["MQM"] + (["DA"] if has_da else []) + metrics)
        direction = "x_to_en" if lp.endswith("-en") else "en_to_x"
        rec = dict(testset=tset, lp=lp, direction=direction, da_protocol=da_protocol, n=len(core),
                   n_systems=core.index.get_level_values(0).nunique(),
                   rho_MQM_vs_DA=spearmanr(core.MQM, core.DA).correlation if has_da else np.nan)
        for lab in ["MQM", "DA"] if has_da else ["MQM"]:
            for m in metrics:
                rec[f"{m}~{lab}"] = spearmanr(core[m], core[lab]).correlation
        # metric-metric agreement on the same set
        for a, b in [("COMET", "chrF"), ("COMET", "BLEURT"), ("COMET", "COMET-QE")]:
            rec[f"{a}~{b}"] = spearmanr(core[a], core[b]).correlation
        rows.append(rec)
        # WMT22 zh-en also has source-based Appraise DA: three labels on one set
        if "DA-appraise" in labels:
            tri = df.dropna(subset=["MQM", "DA", "DA-appraise"] + metrics)
            for lab in ["MQM", "DA", "DA-appraise"]:
                agree_rows.append(dict(testset=tset, lp=lp, label=lab, n=len(tri),
                                       **{m: spearmanr(tri[m], tri[lab]).correlation for m in metrics}))

out = pd.DataFrame(rows)
out.to_csv(ROOT / "results" / "mqm_control.csv", index=False)
tri = pd.DataFrame(agree_rows)
tri.to_csv(ROOT / "results" / "mqm_control_three_labels.csv", index=False)

pd.set_option("display.width", 250)
show = ["testset", "lp", "da_protocol", "n", "n_systems", "rho_MQM_vs_DA", "COMET~MQM", "COMET~DA",
        "chrF~MQM", "chrF~DA", "COMET-QE~MQM", "COMET-QE~DA", "COMET~chrF", "COMET~BLEURT"]
print(out[show].round(3).to_string(index=False))
print("\nmean by direction:")
print(out.groupby("direction")[show[5:]].mean().round(3).to_string())
print("\nmean by direction x DA protocol:")
print(out.groupby(["direction", "da_protocol"])[show[5:]].mean().round(3).to_string())
print("\nWMT22 zh-en, three label types on one segment set:")
print(tri.round(3).to_string(index=False))
