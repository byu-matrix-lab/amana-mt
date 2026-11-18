"""Export AmanaMT v2 per-language metric reliability for the MIRROR-Eval MQM benchmark.

Reads only v2 result files (results/correlations.csv, results/direction_separated_correlations.csv)
and writes results/mirror_eval_reliability.json. That JSON is copied verbatim into MIRROR-Eval
(src/mirroreval/benchmarks/mqm/amanamt_v2_reliability.json); never hand-edit either copy.

Languages: the MIRROR-Eval benchmark's FLORES+ target set. MIRROR-Eval translates en->X, so the
direct evidence is the en->X DA value where v2 separates direction; everything else is marked as
indirect (pooled directions, X->en only, or synthetic labels).
"""
import csv, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANGS = ["de", "zh", "ru", "he", "es", "cs", "tr", "uk", "ha", "km", "ps", "sw", "ht", "lo"]
METRICS = ["bleu", "chrf", "comet"]
# Qualitative caveats stated in the AmanaMT v2 paper (sections cited); no numbers here.
NOTES = {
    "uk": "WMT22 uk-en crowd reference-based DA; near-zero correlation for every metric, attributed in v2 to the "
          "label (into-English crowd reference-based DA), not to the language. Treat as no evidence.",
    "km": "Human labels are X->en DA only (km-en); no en->X evidence.",
    "zh": "Expert MQM, but X->en only (zh-en); no en->X evidence.",
    "he": "Expert MQM, but X->en only (he-en); no en->X evidence.",
    "ps": "Human labels are X->en DA only (ps-en); no en->X evidence.",
    "sw": "Synthetic MQM labels from an LLM judge (v2 Tier 2), not validated against human annotation.",
    "ht": "Synthetic MQM labels from an LLM judge (v2 Tier 2), not validated against human annotation.",
    "lo": "Synthetic MQM labels from an LLM judge (v2 Tier 2), not validated against human annotation.",
    "ha": "en->X DA available; the X->en DA (ha-en) is weak for every metric.",
}

# Language pairs per language, read from v2 segment IDs ("en-de_2020_news_..."). WMT23 he and WMT24 es
# MQM segment IDs carry no pair prefix; their pairs are he-en and en-es (src/mqmbench/data/wmt_mqm.py).
BARE_PREFIX_PAIR = {"he": "he-en", "es": "en-es"}
pairs = {}
for r in csv.DictReader(open(ROOT / "results" / "scores_comet.csv")):
    if r["lang"] in LANGS:
        pre = r["segment_id"].split("_")[0]
        pairs.setdefault(r["lang"], set()).add(pre if "-" in pre else BARE_PREFIX_PAIR.get(pre, pre))
def directions(lang):
    if pairs[lang] == {"flores"}:          # v2 Tier 2: NLLB-200 en->X outputs on FLORES+, synthetic labels
        return ["en_to_x"]
    return sorted({"en_to_x" if p == f"en-{lang}" else "x_to_en" if p == f"{lang}-en" else "x_to_y" for p in pairs[lang]})

pooled = {(r["lang"], r["metric"]): r for r in csv.DictReader(open(ROOT / "results" / "correlations.csv"))}
dirsep = {(r["lang"], r["direction"], r["metric"]): r
          for r in csv.DictReader(open(ROOT / "results" / "direction_separated_correlations.csv"))}
f = lambda x: round(float(x), 3)
out = {}
for lang in LANGS:
    first = pooled[(lang, "comet")]
    entry = {"label_type": first["annotation_tier"], "human_labels": first["annotation_tier"].startswith("human"),
             "domain": first["domain"], "metrics": {}}
    entry["language_pairs"] = sorted(pairs[lang]); entry["directions"] = directions(lang)
    has_enx = all((lang, "en_to_x", m) in dirsep for m in METRICS)
    enx_only = entry["directions"] == ["en_to_x"]          # e.g. en-de MQM: the pooled value IS en->X
    entry["evidence"] = ("direct_en_to_x" if entry["human_labels"] and lang != "uk" and (has_enx or enx_only) else
                         "none" if lang == "uk" or not entry["human_labels"] else "indirect")
    for m in METRICS:
        r = pooled[(lang, m)]
        e = {"pooled": {"spearman_r": f(r["spearman_r"]), "spearman_ci": [f(r["spearman_ci_lo"]), f(r["spearman_ci_hi"])],
                        "pairwise_acc": f(r["pairwise_acc"]), "n": int(r["n"])}}
        if has_enx:
            d = dirsep[(lang, "en_to_x", m)]
            e["en_to_x"] = {"spearman_r": f(d["spearman_r"]), "n": int(d["n"])}
        elif enx_only and entry["human_labels"]:
            e["en_to_x"] = {"spearman_r": e["pooled"]["spearman_r"], "n": e["pooled"]["n"]}
        entry["metrics"][m] = e
    if lang in NOTES:
        entry["note"] = NOTES[lang]
    out[lang] = entry

commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
doc = {"source": "AmanaMT v2 (Thompson and Ringger), revision of ACL Anthology 2026.wmt-main.42",
       "code": "https://github.com/byu-matrix-lab/amana-mt", "amana_mt_commit": commit,
       "generated_by": "scripts/export_mirror_eval_reliability.py",
       "inputs": ["results/correlations.csv", "results/direction_separated_correlations.csv", "results/scores_comet.csv (language pairs)"],
       "statistic": "segment-level Spearman rho with bootstrap 95% CI over source sentences; pairwise_acc as in v2",
       "languages": out}
(ROOT / "results" / "mirror_eval_reliability.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
print({l: (v["evidence"], v["metrics"]["comet"].get("en_to_x", v["metrics"]["comet"]["pooled"])["spearman_r"]) for l, v in out.items()})
