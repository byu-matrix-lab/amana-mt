import sys
from itertools import combinations
from pathlib import Path
import pandas as pd
from scipy.stats import kendalltau
sys.path.insert(0, "scripts/audit")
from mtme_io import read_seg
M = Path(sys.argv[1]) / "wmt22"
def frame(lp, hf, ms):
    c = {"human": read_seg(M / "human-scores" / f"{lp}.{hf}.seg.score")}
    for m in ms: c[m] = read_seg(M / "metric-scores" / lp / f"{m}.seg.score")
    return pd.DataFrame(c)
df = frame("en-de", "mqm", ["COMET-22-refA", "chrF-refA"])
systems = sorted(set(df.index.get_level_values(0)))
print("en-de systems:", systems)
base = df.drop(index=["refA"], level="system", errors="ignore")
mbr = [s for s in systems if "bestmbr" in s]
for name, d in [("drop refA", base), ("drop refA,refB", base.drop(index="refB", level="system", errors="ignore")),
                ("drop refA,refB,mbr", base.drop(index=["refB"] + mbr, level="system", errors="ignore")),
                ("drop refA,mbr", base.drop(index=mbr, level="system", errors="ignore"))]:
    for m in ["COMET-22-refA", "chrF-refA"]:
        x = d[["human", m]].dropna()
        print(f"en-de {name:20s} {m:15s} tau {kendalltau(x[m], x.human).correlation:.3f} n={len(x)}")
# DARR variants on zh-en
z = frame("zh-en", "wmt", ["COMET-22-refA", "chrF-refA", "BLEU-refA"]).drop(index=["refA", "refB"], level="system", errors="ignore")
zz = frame("zh-en", "wmt-z", ["COMET-22-refA"]).drop(index=["refA", "refB"], level="system", errors="ignore")
def darr(d, m, thr, ties):
    c = di = 0
    for _, g in d[["human", m]].dropna().groupby(level="seg"):
        h, s = g.human.values, g[m].values
        for i, j in combinations(range(len(h)), 2):
            if abs(h[i] - h[j]) <= thr: continue
            if s[i] == s[j]:
                if ties == "disc": di += 1
                continue
            if (s[i] > s[j]) == (h[i] > h[j]): c += 1
            else: di += 1
    return (c - di) / (c + di), c + di
for m in ["COMET-22-refA", "chrF-refA", "BLEU-refA"]:
    for thr, ties in [(25, "disc"), (25, "ignore"), (0, "ignore")]:
        t, n = darr(z, m, thr, ties)
        print(f"zh-en DARR raw thr={thr} ties={ties:6s} {m:15s} {t:+.3f} pairs={n}")
print("raw score range:", z.human.min(), z.human.max(), "seg/sys counts:", z.human.notna().sum())
