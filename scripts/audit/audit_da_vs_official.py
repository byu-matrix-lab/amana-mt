"""Audit: do the HF DA labels (RicardoRei/wmt-da-human-evaluation) match WMT's
official segment-level human scores from mt-metrics-eval, for the X->en
year/pairs where metric-human correlation collapses?

Join key is text: (source, system output). If HF labels match the official
ones -> HF is faithful and any problem is in the original WMT annotations.
If they don't -> the HF release misattached labels to segments.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from datasets import load_dataset
from sacrebleu.metrics import CHRF
from scipy.stats import spearmanr

CHRF_PP = CHRF(word_order=2)
ROOT = Path(__file__).resolve().parents[2]
MTME = Path(sys.argv[1])
CASES = [("wmt21.news", 2021, lp) for lp in ("cs-en", "ja-en", "is-en", "ha-en")] + \
        [("wmt22", 2022, lp) for lp in ("cs-en", "ja-en", "uk-en")] + \
        [("wmt20", 2020, lp) for lp in ("cs-en", "ja-en", "pl-en", "ta-en")]  # healthy-year controls

hf = load_dataset("RicardoRei/wmt-da-human-evaluation", split="train").to_pandas()
norm = lambda s: " ".join(str(s).split())


def lines(p):
    return [norm(x) for x in p.read_text(encoding="utf-8").split("\n")[:-1]] if p.exists() else None


rows = []
for tset, year, lp in CASES:
    base = MTME / tset
    src = lines(base / "sources" / f"{lp}.txt")
    hs = sorted((base / "human-scores").glob(f"{lp}.*.seg.score")) if (base / "human-scores").exists() else []
    if src is None or not hs:
        rows.append(dict(testset=tset, lp=lp, note=f"missing: src={src is not None}, human files={len(hs)}"))
        continue
    for hfile in hs:
        scorer = hfile.name[len(lp) + 1:-len(".seg.score")]
        off = pd.read_csv(hfile, sep="\t", header=None, names=["system", "score"], na_values=["None"])
        off["seg"] = off.groupby("system").cumcount()
        recs = []
        for sysname, g in off.dropna(subset=["score"]).groupby("system"):
            out = lines(base / "system-outputs" / lp / f"{sysname}.txt")
            if out is None:
                continue
            for seg, sc in zip(g.seg, g.score):
                if seg < len(src) and seg < len(out):
                    recs.append((src[seg], out[seg], sc))
        offdf = pd.DataFrame(recs, columns=["src", "mt", "official"]).drop_duplicates(["src", "mt"])
        h = hf[(hf.lp == lp) & (hf.year == year)].copy()
        h["src"], h["mt"] = h.src.map(norm), h.mt.map(norm)
        m = h.merge(offdf, on=["src", "mt"], how="inner")
        rho_z = spearmanr(m.score, m.official).correlation if len(m) > 30 else np.nan
        rho_raw = spearmanr(m.raw, m.official).correlation if len(m) > 30 else np.nan
        # which label set carries signal? correlate each with chrF computed from the text
        s = m.sample(min(len(m), 5000), random_state=0) if len(m) else m
        chrf = [CHRF_PP.sentence_score(a, [b]).score for a, b in zip(s.mt, s.ref.map(norm))]
        rho_hf_chrf = spearmanr(s.score, chrf).correlation if len(s) > 30 else np.nan
        rho_off_chrf = spearmanr(s.official, chrf).correlation if len(s) > 30 else np.nan
        same = m.mt == m.ref.map(norm)
        pct_off = m.official.rank(pct=True)[same].mean() if same.sum() >= 20 else np.nan
        pct_hf = m.score.rank(pct=True)[same].mean() if same.sum() >= 20 else np.nan
        rows.append(dict(testset=tset, lp=lp, scorer=scorer, n_hf=len(h), n_official=len(offdf),
                         n_joined=len(m), rho_hf_z_vs_official=round(rho_z, 3),
                         rho_hf_raw_vs_official=round(rho_raw, 3),
                         rho_chrf_vs_hf=round(rho_hf_chrf, 3), rho_chrf_vs_official=round(rho_off_chrf, 3),
                         n_mt_eq_ref=int(same.sum()), pctile_mt_eq_ref_hf=round(pct_hf, 3),
                         pctile_mt_eq_ref_official=round(pct_off, 3)))
        print(rows[-1], flush=True)

out = pd.DataFrame(rows)
out.to_csv(ROOT / "results" / "audit_da_vs_official.csv", index=False)
print("\n" + out.to_string(index=False))
