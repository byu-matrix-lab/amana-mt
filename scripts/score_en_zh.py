"""Score en-zh (English→Chinese) from WMT DA, filling the en→X isolating cell.

The published pipeline never scored en-zh: settings.toml excludes zh from the
DA tier because zh-en is loaded as Tier 1a MQM, and lang_from_pair collapses
both directions to "zh". So the paper's en→X × isolating cell was reported as
having no Tier-1 data, though en-zh DA exists (WMT17-21, ~110k rows).
Advisor feedback (Eric, 2026-10): close this gap.

Annotation protocol: en→X WMT DA was source-based and done by bilingual
annotators/translators, the same protocol as the other en→X DA cells.

Metrics: COMET-22, CometKiwi-23, MetricX-24 (same models and wrappers as
score_de_en.py), plus chrF++ and BLEU via the pipeline wrappers. BLEU is also
computed with sacrebleu's Chinese tokenizer: the pipeline wrapper uses the
default 13a tokenizer, which does not segment Chinese (column bleu_13a keeps
pipeline consistency; bleu_zh is the correct one for a zh target).

Run via SLURM:
  sbatch scripts/slurm/run_score_en_zh.sh
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import sacrebleu
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mqmbench.config import init_settings, settings  # noqa: E402
from mqmbench.data.wmt_da import load_wmt_da  # noqa: E402
from mqmbench.metrics import bleu as bleu_mod  # noqa: E402
from mqmbench.metrics import chrf as chrf_mod  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score_de_en import score_metricx, score_with_model  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS = PROJECT_ROOT / "results"
OUT_PATH = RESULTS / "scores_en_zh.csv"
METRICS = ["comet", "cometkiwi23", "metricx", "chrf", "bleu_13a", "bleu_zh"]


def main():
    init_settings(str(PROJECT_ROOT / "settings.toml"))

    print("Loading en-zh WMT DA data...", flush=True)
    da = load_wmt_da(target_langs=["zh"])
    d = da[da["segment_id"].str.startswith("en-zh")].copy().reset_index(drop=True)
    print(f"  en-zh rows (raw): {len(d)}", flush=True)
    d = d.dropna(subset=["source", "hypothesis"]).reset_index(drop=True)
    print(f"  en-zh rows (clean): {len(d)}", flush=True)
    if d.empty:
        sys.exit("ERROR: no en-zh rows found")

    sources = d["source"].astype(str).tolist()
    hyps = d["hypothesis"].astype(str).tolist()
    refs = d["reference"].fillna("").astype(str).tolist()

    if OUT_PATH.exists() and len(pd.read_csv(OUT_PATH)) == len(d):
        res = pd.read_csv(OUT_PATH)
        print(f"  Resuming from existing results: {list(res.columns)}", flush=True)
    else:
        res = d[["segment_id", "da_score", "quality_score"]].copy()

    def save(col, vals):
        res[col] = vals
        res.to_csv(OUT_PATH, index=False)
        print(f"  {col} done. mean={np.nanmean(vals):.3f}", flush=True)

    # cheap CPU metrics first
    if "chrf" not in res:
        save("chrf", chrf_mod.score(sources, hyps, refs))
    if "bleu_13a" not in res:
        save("bleu_13a", bleu_mod.score(sources, hyps, refs))
    if "bleu_zh" not in res:
        bzh = sacrebleu.BLEU(tokenize="zh", effective_order=True)  # build once, not per sentence
        save("bleu_zh", [bzh.sentence_score(h, [r]).score / 100.0 for h, r in zip(hyps, refs)])

    batch_size = getattr(settings.metrics.comet, "batch_size", 16)
    if "comet" not in res:
        print("Scoring COMET-22...", flush=True)
        save("comet", score_with_model("Unbabel/wmt22-comet-da", sources, hyps, refs,
                                       batch_size=batch_size))
    if "cometkiwi23" not in res:
        print("Scoring CometKiwi-23...", flush=True)
        save("cometkiwi23", score_with_model("Unbabel/wmt23-cometkiwi-da-xl", sources, hyps, refs,
                                             batch_size=batch_size, reference_free=True))
    if "metricx" not in res:
        print("Scoring MetricX-24...", flush=True)
        save("metricx", score_metricx(sources, hyps, refs,
                                      batch_size=getattr(settings.metrics, "metricx_batch_size", 8)))

    # report: pooled and per-year Spearman vs human DA
    res = pd.read_csv(OUT_PATH)
    res["year"] = res.segment_id.str.extract(r"_(\d{4})_")[0]
    rows = []
    for yr, g in [("pooled", res)] + list(res.groupby("year")):
        rec = {"year": yr, "n": len(g)}
        for m in METRICS:
            if m in g:
                v = g[[m, "quality_score"]].dropna()
                rec[m] = spearmanr(v[m], v.quality_score).correlation
        rows.append(rec)
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS / "en_zh_correlations.csv", index=False)
    print("\nen-zh Spearman vs WMT DA (en→X isolating cell)")
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
