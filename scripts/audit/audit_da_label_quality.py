"""Audit: are WMT DA human labels (RicardoRei/wmt-da-human-evaluation) noisy,
or misaligned to their segments, in the years/directions where metric-human
correlation collapses (X->en 2021-2022)?

Reads the raw HF dataset directly (no mqmbench code).

Test 1 (mt == ref): an output identical to the reference is a known-good
translation and should score near the top -- especially in reference-based
into-English DA, where the annotator is shown that exact reference. Aligned
labels -> these rows score well above the rest. Misaligned labels -> no gap.

Test 2 (test-retest): the same (src, mt) pair rated more than once (different
systems produced identical outputs). Aligned-but-noisy labels -> positive
agreement between the ratings. Misaligned labels -> ~0.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from datasets import load_dataset
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
df = load_dataset("RicardoRei/wmt-da-human-evaluation", split="train").to_pandas()
df["direction"] = np.where(df.lp.str.endswith("-en"), "x_to_en",
                           np.where(df.lp.str.startswith("en-"), "en_to_x", "other"))
df = df[df.direction != "other"]
norm = lambda s: s.fillna("").str.strip()
df["src_n"], df["mt_n"], df["ref_n"] = norm(df.src), norm(df.mt), norm(df.ref)

rows = []
for (yr, dr), g in df.groupby(["year", "direction"]):
    # Test 1: identical-to-reference outputs
    same = g.mt_n == g.ref_n
    pct_same = same.mean()
    z_same = g.score[same].mean() if same.sum() >= 20 else np.nan
    z_rest = g.score[~same].mean()
    raw_same = g.raw[same].mean() if same.sum() >= 20 else np.nan
    raw_rest = g.raw[~same].mean()
    # percentile rank of mt==ref rows within the (lp) they belong to
    g = g.assign(pct=g.groupby("lp").score.rank(pct=True))
    pct_rank_same = g.pct[same].mean() if same.sum() >= 20 else np.nan

    # Test 2: test-retest on duplicated (src, mt)
    dup = g[g.duplicated(["lp", "src_n", "mt_n"], keep=False)]
    pairs = []
    for _, grp in dup.groupby(["lp", "src_n", "mt_n"]):
        s = grp.score.values
        if len(s) >= 2:
            pairs.append((s[0], s[1]))
    rr = spearmanr(*zip(*pairs)).correlation if len(pairs) >= 30 else np.nan

    rows.append(dict(year=yr, direction=dr, n=len(g), n_mt_eq_ref=int(same.sum()),
                     pct_mt_eq_ref=round(pct_same * 100, 2),
                     raw_mt_eq_ref=round(raw_same, 1), raw_rest=round(raw_rest, 1),
                     pctile_rank_mt_eq_ref=round(pct_rank_same, 3),
                     n_retest_pairs=len(pairs), retest_rho=round(rr, 3)))

out = pd.DataFrame(rows).sort_values(["direction", "year"])
out.to_csv(ROOT / "results" / "audit_da_label_quality.csv", index=False)
print(out.to_string(index=False))
print("\npctile_rank_mt_eq_ref: mean within-language percentile of mt==ref rows' human score "
      "(0.5 = indistinguishable from average, ~1 = rated at the top)")
