"""Audit: the pipeline's sentence-BLEU uses sacrebleu's default 13a tokenizer for
every target, which does not segment Japanese. Recompute en-ja BLEU with
FLORES-200 SentencePiece tokenization (spBLEU) and see how the en-ja
BLEU-human correlation and the neural-vs-BLEU gap change.

Positional join to the published checkpoints is valid (audit_da_alignment.py:
chrF recompute rho = 1.0 for ja). Sanity check: our 13a recompute must equal
the checkpoint BLEU.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import sacrebleu
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from mqmbench.config import init_settings  # noqa: E402
from mqmbench.data.wmt_da import load_wmt_da  # noqa: E402

init_settings(str(ROOT / "settings.toml"))
d = load_wmt_da(target_langs=["ja"]).reset_index(drop=True)
for m in ["bleu", "chrf", "comet", "metricx", "cometkiwi23"]:
    c = pd.read_csv(ROOT / "results" / f"scores_{m}.csv", usecols=["lang", m])
    c = c[c.lang == "ja"].reset_index(drop=True)
    assert len(c) == len(d), (m, len(c), len(d))
    d[m] = c[m].values
d["direction"] = np.where(d.segment_id.str.startswith("en-ja"), "en_to_x", "x_to_en")

e = d[d.direction == "en_to_x"].copy()
hyp, ref = e.hypothesis.fillna("").astype(str), e.reference.fillna("").astype(str)
# build each scorer ONCE: sacrebleu.sentence_bleu re-instantiates BLEU (and reloads the
# SentencePiece model) on every call, which exhausted 64G over ~24k calls
b13a = sacrebleu.BLEU(effective_order=True)
bspm = sacrebleu.BLEU(tokenize="flores200", effective_order=True)
e["bleu_13a_recomputed"] = [b13a.sentence_score(h, [r]).score / 100 for h, r in zip(hyp, ref)]
e["bleu_spm"] = [bspm.sentence_score(h, [r]).score / 100 for h, r in zip(hyp, ref)]
match = np.isclose(e.bleu_13a_recomputed, e.bleu, atol=1e-9).mean()
print(f"en-ja rows: {len(e)}   13a recompute == checkpoint BLEU: {match:.4f}")
print(f"mean whitespace tokens per ja hypothesis: {hyp.str.split().str.len().mean():.2f}")

rows = []
for col in ["bleu", "bleu_spm", "chrf", "comet", "metricx", "cometkiwi23"]:
    rows.append(dict(metric=col, rho=spearmanr(e[col], e.quality_score).correlation))
    for yr, g in e.groupby(e.segment_id.str.extract(r"_(\d{4})_")[0]):
        rows[-1][f"rho_{yr}"] = spearmanr(g[col], g.quality_score).correlation
out = pd.DataFrame(rows)
out.loc[len(out)] = dict(metric="COMET minus BLEU(13a)", rho=out.rho[out.metric == "comet"].item() - out.rho[out.metric == "bleu"].item())
out.loc[len(out)] = dict(metric="COMET minus spBLEU", rho=out.rho[out.metric == "comet"].item() - out.rho[out.metric == "bleu_spm"].item())
out.to_csv(ROOT / "results" / "audit_bleu_tokenization_ja.csv", index=False)
print(out.round(3).to_string(index=False))
