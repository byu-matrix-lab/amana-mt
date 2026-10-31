"""Audit: are the per-metric DA checkpoint rows positionally aligned with the
DA dataset rows they're joined to?

Every DA-tier number in the paper joins scores_{metric}.csv to the DA data by
position (segment_id is a non-unique domain key like "fi-en_2020_news"). The
checkpoints store no text, so alignment can't be checked by text. Instead:
recompute sentence chrF from each DA row's own hypothesis/reference at a
sample of positions and correlate it with the checkpoint's chrF at the same
positions. Aligned -> Spearman ~1. Misaligned -> ~0.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sacrebleu.metrics import CHRF
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from mqmbench.data.wmt_da import load_wmt_da  # row set + order the analysis uses

LANGS = ["fi", "tr", "et", "lt", "cs", "ja", "kk", "ta", "ha", "pl", "is", "gu",
         "lv", "ps", "km", "uk", "bn", "fr", "hi", "xh", "zu"]
SAMPLE = 3000
rng = np.random.default_rng(0)

da = load_wmt_da(target_langs=LANGS)
ckpt = pd.read_csv(ROOT / "results" / "scores_chrf.csv")
chrf_plain, chrf_pp = CHRF(), CHRF(word_order=2)

rows = []
for lang in LANGS:
    d = da[da.lang == lang].reset_index(drop=True)
    c = ckpt[ckpt.lang == lang].reset_index(drop=True)
    n = min(len(d), len(c))
    idx = np.sort(rng.choice(n, size=min(SAMPLE, n), replace=False))
    seg_match = float((d.segment_id.values[idx] == c.segment_id.values[idx]).mean())
    mine_plain = [chrf_plain.sentence_score(d.hypothesis[i], [d.reference[i]]).score for i in idx]
    mine_pp = [chrf_pp.sentence_score(d.hypothesis[i], [d.reference[i]]).score for i in idx]
    theirs = c.chrf.values[idx]
    rho_plain = spearmanr(mine_plain, theirs).correlation
    rho_pp = spearmanr(mine_pp, theirs).correlation
    # control: same comparison against a random permutation (what misalignment looks like)
    rho_shuffled = spearmanr(mine_pp, rng.permutation(theirs)).correlation
    rows.append(dict(lang=lang, n_da=len(d), n_ckpt=len(c), segid_match=round(seg_match, 4),
                     rho_chrF=round(rho_plain, 4), rho_chrFpp=round(rho_pp, 4),
                     rho_shuffled_control=round(rho_shuffled, 4)))
    print(rows[-1], flush=True)

out = pd.DataFrame(rows)
out.to_csv(ROOT / "results" / "audit_da_alignment.csv", index=False)
print("\n" + out.to_string(index=False))
