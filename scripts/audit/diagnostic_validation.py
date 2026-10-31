"""Do cheap, MQM-free label diagnostics predict how well DA agrees with expert MQM?

Per (year, lp) slice with both labels (results/mqm_control.csv):
  D1 mt==ref percentile: mean within-slice percentile of the DA z-score of outputs
     identical to the reference (HF RicardoRei data; WMT20-22 only). ~0.5 = labels blind.
  D2 metric-metric minus metric-human: COMET~BLEURT minus COMET~DA (same segments).
     Large gap = metrics agree with each other but not with the labels.
Target: rho(MQM, DA) on the identical segments.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from datasets import load_dataset
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
ctl = pd.read_csv(ROOT / "results" / "mqm_control.csv").dropna(subset=["rho_MQM_vs_DA"])
ctl["year"] = ctl.testset.str[3:5].astype(int) + 2000
ctl["D2_mm_minus_mh"] = ctl["COMET~BLEURT"] - ctl["COMET~DA"]

hf = load_dataset("RicardoRei/wmt-da-human-evaluation", split="train").to_pandas()
d1 = []
for _, r in ctl.iterrows():
    g = hf[(hf.lp == r.lp) & (hf.year == r.year)]
    if g.empty:
        d1.append((np.nan, 0)); continue
    same = g.mt.fillna("").str.strip() == g.ref.fillna("").str.strip()
    pct = g.score.rank(pct=True)
    d1.append((pct[same].mean() if same.sum() >= 20 else np.nan, int(same.sum())))
ctl["D1_mt_eq_ref_pctile"], ctl["n_mt_eq_ref"] = zip(*d1)

cols = ["testset", "lp", "da_protocol", "rho_MQM_vs_DA", "D1_mt_eq_ref_pctile", "n_mt_eq_ref", "D2_mm_minus_mh"]
out = ctl[cols]
out.to_csv(ROOT / "results" / "followup_diagnostic_validation.csv", index=False)
print(out.round(3).to_string(index=False))
for dcol in ["D1_mt_eq_ref_pctile", "D2_mm_minus_mh"]:
    s = out.dropna(subset=[dcol])
    r = spearmanr(s[dcol], s.rho_MQM_vs_DA)
    print(f"\n{dcol}: Spearman with rho(MQM,DA) = {r.correlation:.3f} (p = {r.pvalue:.3f}, n = {len(s)} slices)")
