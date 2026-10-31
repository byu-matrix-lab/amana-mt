"""Audit: does the en->X > X->en reliability gap survive when direction is
compared within the same WMT year (same shared-task edition) for the same
language? Positional join is valid here: audit_da_alignment.py verified the
checkpoints align row-for-row with load_wmt_da (chrF++ recompute rho = 1.0).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, wilcoxon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from mqmbench.data.wmt_da import load_wmt_da

MIXED = ["fi", "tr", "et", "lt", "cs", "ja", "kk", "ta", "ha", "pl", "is", "gu"]
METRICS = ["comet", "bleu", "chrf", "metricx", "cometkiwi23"]

da = load_wmt_da(target_langs=MIXED)
ck = {m: pd.read_csv(ROOT / "results" / f"scores_{m}.csv", usecols=["lang", m]) for m in METRICS}

rows = []
for lang in MIXED:
    d = da[da.lang == lang].reset_index(drop=True).copy()
    for m in METRICS:
        c = ck[m][ck[m].lang == lang].reset_index(drop=True)
        assert len(c) == len(d), (lang, m, len(c), len(d))
        d[m] = c[m].values
    parts = d.segment_id.str.extract(r"^([a-z]+)-([a-z]+)_(\d{4})_")
    d["direction"] = np.where(parts[1] == "en", "x_to_en", np.where(parts[0] == "en", "en_to_x", "pivot"))
    d["year"] = parts[2]
    for (yr, dr), g in d[d.direction != "pivot"].groupby(["year", "direction"]):
        rec = dict(lang=lang, year=yr, direction=dr, n=len(g))
        for m in METRICS:
            rec[m] = spearmanr(g[m], g.quality_score).correlation
        # metric-metric agreement: if metrics agree with EACH OTHER but not with
        # humans, the human labels (not the metrics) are the unreliable party
        rec["comet~metricx"] = spearmanr(g.comet, g.metricx).correlation
        rec["comet~ck23"] = spearmanr(g.comet, g.cometkiwi23).correlation
        rec["comet~chrf"] = spearmanr(g.comet, g.chrf).correlation
        rows.append(rec)

cells = pd.DataFrame(rows)
cells.to_csv(ROOT / "results" / "audit_direction_by_year.csv", index=False)

wide = cells.pivot_table(index=["lang", "year"], columns="direction", values=METRICS + ["n", "comet~metricx", "comet~ck23", "comet~chrf"])
matched = wide.dropna(subset=[("comet", "en_to_x"), ("comet", "x_to_en")])
print(f"Same-language, same-year cells with BOTH directions: {len(matched)}\n")
for m in METRICS:
    gap = matched[(m, "en_to_x")] - matched[(m, "x_to_en")]
    p = wilcoxon(gap).pvalue if len(gap) >= 6 else float("nan")
    print(f"{m:12s} mean(en->X - X->en) = {gap.mean():+.3f}   en->X wins {int((gap > 0).sum())}/{len(gap)}   Wilcoxon p = {p:.4f}")
print()
show = matched[[("comet", "en_to_x"), ("comet", "x_to_en"), ("bleu", "en_to_x"), ("bleu", "x_to_en"),
                ("n", "en_to_x"), ("n", "x_to_en")]].round(3)
print(show.to_string())

print("\n=== metric-metric agreement vs metric-human, same-year matched cells ===")
agree = ["comet~metricx", "comet~ck23", "comet~chrf"]
for col in agree + ["comet"]:
    a = matched[(col, "en_to_x")]; b = matched[(col, "x_to_en")]
    print(f"{col:14s} en->X mean {a.mean():.3f}   X->en mean {b.mean():.3f}   gap {(a-b).mean():+.3f}")
print()
print(matched[[("comet","en_to_x"),("comet","x_to_en"),("comet~metricx","en_to_x"),("comet~metricx","x_to_en")]].round(3).to_string())
