"""System-level check: does corpus chrF per system track WMT's official
system-level human scores, for X->en years where segment-level labels carry
no signal? Healthy system-level + dead segment-level = labels informative only
in aggregate. Both dead = raters effectively random."""
import sys
from pathlib import Path
import pandas as pd
from sacrebleu.metrics import CHRF
from scipy.stats import pearsonr, spearmanr

MTME = Path(sys.argv[1]); ROOT = Path(__file__).resolve().parents[2]
chrf = CHRF(word_order=2)
CASES = [("wmt20", lp) for lp in ("cs-en", "ja-en", "pl-en", "ta-en")] + \
        [("wmt21.news", lp) for lp in ("cs-en", "ja-en", "is-en", "ha-en")] + \
        [("wmt22", lp) for lp in ("cs-en", "ja-en", "uk-en")]
rows = []
for t, lp in CASES:
    b = MTME / t
    hfile = next(iter(sorted((b / "human-scores").glob(f"{lp}.*z.sys.score"))), None)
    reffile = next(iter(sorted((b / "references").glob(f"{lp}.*.txt"))), None)
    hum = pd.read_csv(hfile, sep="\t", header=None, names=["system", "human"], na_values=["None"]).dropna()
    ref = reffile.read_text(encoding="utf-8").split("\n")[:-1]
    scores = {}
    for s in hum.system:
        p = b / "system-outputs" / lp / f"{s}.txt"
        if p.exists():
            hyp = p.read_text(encoding="utf-8").split("\n")[:-1]
            scores[s] = chrf.corpus_score(hyp, [ref]).score
    h = hum[hum.system.isin(scores)]
    h = h[~h.system.str.startswith("ref")]  # drop human references scored as systems
    x = [scores[s] for s in h.system]
    rows.append(dict(testset=t, lp=lp, n_systems=len(h), ref=reffile.name,
                     sys_pearson=round(pearsonr(x, h.human)[0], 3), sys_spearman=round(spearmanr(x, h.human)[0], 3)))
    print(rows[-1], flush=True)
out = pd.DataFrame(rows); out.to_csv(ROOT / "results" / "audit_da_system_level.csv", index=False)
print("\n" + out.to_string(index=False))
