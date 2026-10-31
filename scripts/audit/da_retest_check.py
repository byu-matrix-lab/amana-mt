"""Are DA 'test-retest' pairs (same lp, src, mt rated under different systems)
independent ratings, or one rating copied to every system that produced the
identical output? Exact-equal raw scores => copied (WMT annotates duplicates once)."""
from pathlib import Path

import numpy as np
import pandas as pd
from datasets import load_dataset

ROOT = Path(__file__).resolve().parents[2]
df = load_dataset("RicardoRei/wmt-da-human-evaluation", split="train").to_pandas()
df["direction"] = np.where(df.lp.str.endswith("-en"), "x_to_en",
                           np.where(df.lp.str.startswith("en-"), "en_to_x", "other"))
df = df[df.direction != "other"]
for c in ("src", "mt"):
    df[c] = df[c].fillna("").str.strip()
rows = []
for (yr, dr), g in df.groupby(["year", "direction"]):
    dup = g[g.duplicated(["lp", "src", "mt"], keep=False)]
    pairs = [grp.raw.values[:2] for _, grp in dup.groupby(["lp", "src", "mt"]) if len(grp) >= 2]
    if not pairs:
        continue
    a = np.array(pairs)
    rows.append(dict(year=yr, direction=dr, n_pairs=len(a),
                     frac_raw_exactly_equal=float((a[:, 0] == a[:, 1]).mean()),
                     mean_abs_diff_raw=float(np.abs(a[:, 0] - a[:, 1]).mean())))
out = pd.DataFrame(rows)
out.to_csv(ROOT / "results" / "followup_da_retest_check.csv", index=False)
print(out.round(3).to_string(index=False))
