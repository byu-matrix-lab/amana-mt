"""Validate the audit loader (mtme_io.read_seg) against numbers WMT published.

WMT22 Metrics findings (Freitag et al. 2022):
  Table 11: segment-level Kendall tau vs MQM (flattened over systems x segments).
            Column order (verified by exact zh-en reproduction): "human incl." precedes "no human".
            zh-en COMET-22 .428 (no human) / .420 (human incl.); chrF .147/.146;
            BLEU .145/.143; metricx_xxl_MQM_2020 .427/.421; en-de COMET-22 .368/.361.
  Table 13: segment-level Kendall-like (DARR) vs crowd Ref. DA, no human translations,
            zh-en COMET-22 .002, chrF .025, BLEU .024, f200spBLEU .026.
"""
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mtme_io import read_seg  # noqa: E402

M = Path(sys.argv[1]) / "wmt22"
METRICS = {"COMET-22": "COMET-22-refA", "chrF": "chrF-refA", "BLEU": "BLEU-refA",
           "metricx_xxl_MQM_2020": "metricx_xxl_MQM_2020-refA", "f200spBLEU": "f200spBLEU-refA"}
# (no human, human incl.)
PUB11 = {("zh-en", "COMET-22"): (.428, .420), ("zh-en", "chrF"): (.147, .146), ("zh-en", "BLEU"): (.145, .143),
         ("zh-en", "metricx_xxl_MQM_2020"): (.427, .421), ("en-de", "COMET-22"): (.368, .361),
         ("en-de", "chrF"): (.214, .208), ("en-de", "BLEU"): (.169, .164)}
PUB13 = {"COMET-22": .002, "chrF": .025, "BLEU": .024, "f200spBLEU": .026, "metricx_xxl_MQM_2020": -.003}


def frame(lp, human_file):
    cols = {"human": read_seg(M / "human-scores" / f"{lp}.{human_file}.seg.score")}
    for m, stem in METRICS.items():
        cols[m] = read_seg(M / "metric-scores" / lp / f"{stem}.seg.score")
    return pd.DataFrame(cols)


print("=== Table 11: Kendall tau vs MQM (flattened)")
for lp in ["zh-en", "en-de"]:
    df = frame(lp, "mqm")
    for incl, label in [(False, "no human"), (True, "human incl.")]:
        d = df.drop(index="refA", level="system", errors="ignore")  # metrics use refA: unscorable
        if not incl:
            d = d.drop(index="refB", level="system", errors="ignore")
        for m in METRICS:
            if (lp, m) not in PUB11:
                continue
            x = d[["human", m]].dropna()
            tau = kendalltau(x[m], x.human).correlation
            pub = PUB11[(lp, m)][int(incl)]
            print(f"{lp} {label:12s} {m:22s} ours {tau:.3f}  published {pub:.3f}  diff {tau - pub:+.3f}  n={len(x)}")

print("\n=== Table 13: DARR Kendall-like vs crowd Ref. DA (raw scores, |diff| > 25, no human)")
df = frame("zh-en", "wmt").drop(index=["refA", "refB"], level="system", errors="ignore")
for m in PUB13:
    conc = disc = 0
    for _, g in df[["human", m]].dropna().groupby(level="seg"):
        h, s = g.human.values, g[m].values
        for i, j in combinations(range(len(h)), 2):
            if abs(h[i] - h[j]) <= 25:
                continue
            better_h = h[i] > h[j]
            if s[i] == s[j]:
                disc += 1  # WMT DARR: metric ties count as discordant
            elif (s[i] > s[j]) == better_h:
                conc += 1
            else:
                disc += 1
    tau = (conc - disc) / (conc + disc)
    print(f"zh-en {m:22s} ours {tau:.3f}  published {PUB13[m]:.3f}  diff {tau - PUB13[m]:+.3f}  pairs={conc + disc}")
