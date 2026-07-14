#!/usr/bin/env python3
r"""
Generate paper_stats.json (SSOT) and latex/macros.tex from results CSVs.

Every numeric claim in the paper should trace to an entry here.
Manual entries (year-stratified values not in CSVs) are marked source="manual/*".

Run from the project root:
    python3 scripts/generate_macros.py

Outputs:
    results/paper_stats.json  — single source of truth for all paper statistics
    latex/macros.tex          — \newcommand definitions; \input{macros} in main.tex
"""

import json
import math
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
RESULTS = ROOT / "results"
LATEX = ROOT / "latex"

# Correct morphological classification — must match src/mqmbench/analysis/correlation.py
MORPHOLOGY: dict[str, set[str]] = {
    "isolating":    {"zh", "th", "lo", "km", "my"},
    "agglutinative": {"tr", "fi", "et", "ka", "kk", "sw", "am", "ja", "ta"},
    "fusional":     {"de", "ru", "es", "cs", "fr", "pl", "uk", "is", "lt", "lv",
                     "he", "ps", "bn", "hi", "gu", "xh", "zu", "ha", "ht"},
}


def morph_of(lang: str) -> str:
    for m, langs in MORPHOLOGY.items():
        if lang in langs:
            return m
    return "unknown"


# --- Formatting helpers (produce LaTeX-ready strings) ---

def fmt_rho(v) -> str:
    """Correlation as .XXX, no leading zero."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return r"\text{---}"
    s = f"{v:.3f}"
    return s.lstrip("0") if s != "0.000" else ".000"


def fmt_spa(v) -> str:
    return fmt_rho(v)


def fmt_eta(v) -> str:
    return f"{v:.3f}"


def fmt_n(v) -> str:
    """Integer with LaTeX thousand separator: 49{,}741"""
    return f"{int(v):,}".replace(",", "{,}")


def fmt_t(v) -> str:
    """t-statistic as integer with sign and thousand sep."""
    i = int(round(v))
    sign = "+" if i > 0 else ""
    return sign + f"{i:,}".replace(",", "{,}")


def fmt_pval(v) -> str:
    """Scientific notation p-value for LaTeX."""
    if v == 0.0:
        return "0"
    # e.g. 7.229407e-08 → 7.2\times10^{-8}
    exp = int(math.floor(math.log10(abs(v))))
    mantissa = v / (10 ** exp)
    return rf"{mantissa:.1f}\times10^{{{exp}}}"


# ─────────────────────────────────────────────────────────────────────────────
# Load CSVs
# ─────────────────────────────────────────────────────────────────────────────
tier_df = pd.read_csv(RESULTS / "tier_summary.csv")
da_df   = pd.read_csv(RESULTS / "direction_analysis.csv")
dm_df   = pd.read_csv(RESULTS / "direction_morphology_interaction.csv")
wt_df   = pd.read_csv(RESULTS / "williams_tests.csv")
corr_df = pd.read_csv(RESULTS / "correlations.csv")

stats: dict[str, dict] = {}  # macro_name -> {value, fmt, source, note}


def add(key: str, value, fmt_value: str, source: str, note: str = "") -> None:
    if key in stats:
        raise ValueError(f"Duplicate key: {key}")
    stats[key] = {"value": value, "fmt": fmt_value, "source": source, "note": note}


# ─────────────────────────────────────────────────────────────────────────────
# META
# ─────────────────────────────────────────────────────────────────────────────
n_langs_actual = int(corr_df.lang.nunique())
add("TotalSegments", 730748, fmt_n(730748), "manual/pipeline_run",
    "Total segments across all tiers: MQM_HF(150347) + DA(549587) + Tier2(7084) + span_fallback(23730)")
add("NumLanguages", n_langs_actual, str(n_langs_actual), "correlations.csv",
    "Unique languages with valid entries in correlations.csv")
add("NumMetrics", 10, "10", "manual",
    "bleu chrf bertscore bleurt comet xcomet metricx cometkiwi cometkiwi23 gemba")

# ─────────────────────────────────────────────────────────────────────────────
# TIER MEANS  (Table 1)
# ─────────────────────────────────────────────────────────────────────────────
METRIC_KEY = {
    "bleu": "BLEU", "chrf": "ChrF", "bertscore": "BERTScore",
    "bleurt": "BLEURT", "comet": "COMET", "xcomet": "xCOMET",
    "metricx": "MetricX", "cometkiwi": "KiwiXXII", "cometkiwi23": "KiwiXXIII",
    "gemba": "GEMBA", "ensemble": "Ensemble",
}
TIER_KEY = {"high": "High", "medium": "Med", "low": "Low"}

# Group by (metric, resource_tier) across annotation tiers (e.g., human_da + human_mqm at medium)
# and average — tier = resource level, not annotation method.
_tier_grouped = (
    tier_df[tier_df.annotation_tier != "synthetic_mqm"]
    .groupby(["metric", "resource_tier"], as_index=False)
    [["spearman_r", "spa"]]
    .mean(numeric_only=True)
)
for _, row in _tier_grouped.iterrows():
    mk = METRIC_KEY.get(row.metric, row.metric.capitalize())
    tk = TIER_KEY.get(row.resource_tier, row.resource_tier.capitalize())

    rho = row.spearman_r
    spa = row.spa if not pd.isna(row.spa) else None

    if not pd.isna(rho):
        add(f"Tier{mk}{tk}Rho", float(rho), fmt_rho(rho), "tier_summary.csv",
            f"{row.metric} mean Spearman rho, {row.resource_tier} tier (averaged across annotation tiers)")
    if spa is not None:
        add(f"Tier{mk}{tk}SPA", float(spa), fmt_spa(spa), "tier_summary.csv",
            f"{row.metric} mean SPA, {row.resource_tier} tier (averaged across annotation tiers)")

# ─────────────────────────────────────────────────────────────────────────────
# PER-LANGUAGE COMET + METRICX  (heatmap, appendix table, text)
# ─────────────────────────────────────────────────────────────────────────────
for lang in sorted(da_df.lang.unique()):
    for metric in ("comet", "metricx", "cometkiwi23"):
        rows = da_df[(da_df.lang == lang) & (da_df.metric == metric)]
        if rows.empty:
            continue
        row = rows.iloc[0]
        if pd.isna(row.spearman_r):
            continue
        if metric == "comet":
            mk = "COMET"
        elif metric == "metricx":
            mk = "MetricX"
        else:
            mk = "KiwiXXIII"
        add(f"Lang{mk}{lang.upper()}", float(row.spearman_r), fmt_rho(row.spearman_r),
            "direction_analysis.csv",
            f"{lang} {metric} rho (direction={row.direction}, tier={row.resource_tier})")

# Per-language N (one entry per lang, from COMET row)
for lang in sorted(da_df.lang.unique()):
    rows = da_df[(da_df.lang == lang) & (da_df.metric == "comet")]
    if rows.empty:
        continue
    row = rows.iloc[0]
    if pd.isna(row.n):
        continue
    add(f"LangN{lang.upper()}", int(row.n), fmt_n(row.n), "direction_analysis.csv",
        f"Segment count for {lang}")

# Bootstrap CIs for de and ps (from correlations.csv — has CI columns)
for lang in ("de", "ps"):
    row = corr_df[(corr_df.lang == lang) & (corr_df.metric == "comet")].iloc[0]
    add(f"LangCOMET{lang.upper()}CIlo", float(row.spearman_ci_lo),
        fmt_rho(row.spearman_ci_lo), "correlations.csv",
        f"{lang} COMET 95% bootstrap CI lower bound")
    add(f"LangCOMET{lang.upper()}CIhi", float(row.spearman_ci_hi),
        fmt_rho(row.spearman_ci_hi), "correlations.csv",
        f"{lang} COMET 95% bootstrap CI upper bound")

# Ukrainian p-value (domain outlier, near 0.19)
uk_row = corr_df[(corr_df.lang == "uk") & (corr_df.metric == "comet")].iloc[0]
add("LangUKCOMETPval", float(uk_row.spearman_p), f"{uk_row.spearman_p:.2f}",
    "correlations.csv", "Ukrainian COMET Spearman p-value (domain outlier)")

# ─────────────────────────────────────────────────────────────────────────────
# DIRECTION × MORPHOLOGY  (Table 2)
# Recomputed from direction_analysis.csv using corrected MORPHOLOGY dict.
# The stored direction_morphology_interaction.csv is STALE for x_to_en cells
# because km was reclassified from agglutinative → isolating after that CSV was
# generated.  We recompute cell means here from the per-language data.
# ─────────────────────────────────────────────────────────────────────────────
da_t1 = da_df[
    (da_df.metric == "comet") & (da_df.domain != "unknown")
].copy()
da_t1["morphology"] = da_t1.lang.apply(morph_of)

DIR_KEY  = {"en_to_x": "EntoX", "x_to_en": "XtoEn", "pivot": "Pivot"}
MORPH_KEY = {"agglutinative": "Agglutin", "fusional": "Fusional", "isolating": "Isolating"}

CELLS = [
    ("en_to_x", "agglutinative"),
    ("en_to_x", "fusional"),
    ("x_to_en", "isolating"),
    ("x_to_en", "agglutinative"),
    ("x_to_en", "fusional"),
    ("pivot",   "fusional"),
]

for direction, morph_type in CELLS:
    subset = da_t1[
        (da_t1.direction == direction) & (da_t1.morphology == morph_type)
    ].dropna(subset=["spearman_r"])
    if subset.empty:
        continue
    mean_rho = float(subset.spearman_r.mean())
    langs_in_cell = sorted(subset.lang.tolist())
    dk  = DIR_KEY[direction]
    mk2 = MORPH_KEY[morph_type]
    add(f"DirMorphCOMET{dk}{mk2}", mean_rho, fmt_rho(mean_rho),
        "direction_analysis.csv (recomputed with corrected morphology)",
        f"COMET mean rho: {direction} × {morph_type}. N={len(subset)} langs: {langs_in_cell}")

# CIs for cells with n≥3 — from the interaction CSV (only non-x_to_en cells
# are unaffected by the km reclassification, so their CIs are still valid)
comet_dm = dm_df[dm_df.metric == "comet"].set_index(["direction", "morphology_type"])
CI_CELLS = [
    ("en_to_x", "agglutinative", "EntoXAgglutin"),
    ("en_to_x", "fusional",      "EntoXFusional"),
    ("x_to_en", "fusional",      "XtoEnFusional"),
    ("pivot",   "fusional",      "PivotFusional"),
]
for direction, morph_type, suffix in CI_CELLS:
    try:
        row = comet_dm.loc[(direction, morph_type)]
    except KeyError:
        continue
    if not pd.isna(row.ci_lo):
        add(f"DirMorphCOMET{suffix}CIlo", float(row.ci_lo), fmt_rho(row.ci_lo),
            "direction_morphology_interaction.csv",
            f"COMET bootstrap CI lower: {direction} × {morph_type}")
        add(f"DirMorphCOMET{suffix}CIhi", float(row.ci_hi), fmt_rho(row.ci_hi),
            "direction_morphology_interaction.csv",
            f"COMET bootstrap CI upper: {direction} × {morph_type}")

# η² from the interaction CSV (same value on every row for a given metric)
comet_dm_first = dm_df[dm_df.metric == "comet"].iloc[0]
add("EtaSqInteract", float(comet_dm_first.interaction_eta_sq),
    fmt_eta(comet_dm_first.interaction_eta_sq),
    "direction_morphology_interaction.csv", "η² interaction term (ANOVA on per-lang COMET rho)")
add("EtaSqDir",      float(comet_dm_first.direction_eta_sq),
    fmt_eta(comet_dm_first.direction_eta_sq),
    "direction_morphology_interaction.csv", "η² direction main effect")
add("EtaSqMorph",    float(comet_dm_first.morphology_eta_sq),
    fmt_eta(comet_dm_first.morphology_eta_sq),
    "direction_morphology_interaction.csv", "η² morphology main effect")

# ─────────────────────────────────────────────────────────────────────────────
# PER-DIRECTION PER-METRIC MEANS  (Table 3)
# Tier 1 only (exclude synthetic/unknown domain)
# ─────────────────────────────────────────────────────────────────────────────
da_t1_all = da_df[da_df.domain != "unknown"].copy()

TABLE3_METRICS = {
    "bleu": "BLEU", "chrf": "ChrF", "comet": "COMET",
    "xcomet": "xCOMET", "metricx": "MetricX",
}
for direction in ("en_to_x", "x_to_en", "pivot"):
    dk = DIR_KEY[direction]
    for metric, mk3 in TABLE3_METRICS.items():
        subset = da_t1_all[
            (da_t1_all.direction == direction) & (da_t1_all.metric == metric)
        ].dropna(subset=["spearman_r"])
        mean_rho = float(subset.spearman_r.mean())
        add(f"DirMetric{mk3}{dk}", mean_rho, fmt_rho(mean_rho),
            "direction_analysis.csv",
            f"Mean Spearman rho: {direction} × {metric} (n={len(subset)} langs)")

# ─────────────────────────────────────────────────────────────────────────────
# WILLIAMS TESTS
# ─────────────────────────────────────────────────────────────────────────────
wt_valid = wt_df[wt_df.metric != "ensemble"].dropna(subset=["t_statistic"])

max_row = wt_valid.loc[wt_valid.t_statistic.idxmax()]
min_row = wt_valid.loc[wt_valid.t_statistic.idxmin()]

# n range across all Williams-tested languages (all tiers with valid t-stats)
wt_all_valid = wt_df.dropna(subset=["t_statistic"])
wt_n_min_row = wt_all_valid.loc[wt_all_valid.n.idxmin()]
wt_n_max_row = wt_all_valid.loc[wt_all_valid.n.idxmax()]
add("WilliamsNMin", int(wt_n_min_row.n), fmt_n(wt_n_min_row.n), "williams_tests.csv",
    f"Smallest n across Williams-tested languages (lang={wt_n_min_row.lang})")
add("WilliamsNMax", int(wt_n_max_row.n), fmt_n(wt_n_max_row.n), "williams_tests.csv",
    f"Largest n across Williams-tested languages (lang={wt_n_max_row.lang})")

add("WilliamsMaxT", float(max_row.t_statistic), fmt_t(max_row.t_statistic),
    "williams_tests.csv",
    f"Max Williams t: lang={max_row.lang} metric={max_row.metric} vs {max_row.reference_metric} n={max_row.n}")
add("WilliamsMinT", float(min_row.t_statistic), fmt_t(min_row.t_statistic),
    "williams_tests.csv",
    f"Min Williams t: lang={min_row.lang} metric={min_row.metric} vs {min_row.reference_metric} n={min_row.n}")

# Zulu xCOMET vs COMET — only non-underflow comparison mentioned in paper
zu_row = wt_df[
    (wt_df.lang == "zu") & (wt_df.metric == "xcomet") & (wt_df.reference_metric == "comet")
].iloc[0]
add("ZuluXcometPval", float(zu_row.p_value), fmt_pval(zu_row.p_value),
    "williams_tests.csv", "Zulu xCOMET vs COMET Williams p-value")

# ─────────────────────────────────────────────────────────────────────────────
# MANUAL ENTRIES
# Year-stratified Russian and German values are not in the CSVs — they require
# running the correlation analysis on year-split subsets of the MQM data.
# These were computed ad-hoc during analysis and are marked manual until a
# dedicated year_stratified_correlations.csv is generated.
# ─────────────────────────────────────────────────────────────────────────────
add("RuWmtOneRho", 0.383, ".383", "manual/year_stratified",
    "Russian WMT21-only COMET Spearman rho (year-split subset analysis)")
add("RuWmtTwoRho", 0.501, ".501", "manual/year_stratified",
    "Russian WMT22-only COMET Spearman rho (year-split subset analysis)")
add("RuWmtOneN", 15600, fmt_n(15600), "manual/year_stratified",
    "Russian WMT21 approximate segment count")
add("RuWmtTwoN", 19725, fmt_n(19725), "manual/year_stratified",
    "Russian WMT22 approximate segment count")

add("DeWmtTwoZeroRho", 0.497, ".497", "manual/year_stratified",
    "German WMT2020 COMET rho (year-split subset analysis)")
add("DeWmtTwoOneRho",  0.323, ".323", "manual/year_stratified",
    "German WMT2021 COMET rho (year-split subset analysis)")
add("DeWmtTwoTwoRho",  0.456, ".456", "manual/year_stratified",
    "German WMT2022 COMET rho (year-split subset analysis)")

# ─────────────────────────────────────────────────────────────────────────────
# WRITE OUTPUTS
# ─────────────────────────────────────────────────────────────────────────────

# paper_stats.json
json_out = {}
for key, data in stats.items():
    json_out[key] = {
        "value":  data["value"],
        "fmt":    data["fmt"],
        "source": data["source"],
        "note":   data["note"],
    }
with open(RESULTS / "paper_stats.json", "w") as f:
    json.dump(json_out, f, indent=2, default=str)
print(f"Wrote {len(json_out)} entries → results/paper_stats.json")

# macros.tex — skip entries whose values are not numeric (string-only labels)
lines = [
    r"% Auto-generated by scripts/generate_macros.py — DO NOT EDIT BY HAND",
    r"% Source of truth: results/paper_stats.json",
    r"% Regenerate: python3 scripts/generate_macros.py",
    r"%",
]

# Section headers for readability
SECTIONS = {
    "TotalSegments":        "% --- Meta ---",
    "TierBLEUHighRho":      "% --- Tier means (Table 1) ---",
    "LangCOMETAM":          "% --- Per-language COMET rho ---",
    "LangMetricXAM":        "% --- Per-language MetricX rho ---",
    "LangNAM":              "% --- Per-language N ---",
    "LangCOMETDECIlo":      "% --- Bootstrap CIs (de, ps) ---",
    "LangUKCOMETPval":      "% --- Ukrainian p-value ---",
    "DirMorphCOMETEntoXAgglutin": "% --- Direction x Morphology cell means (Table 2) ---",
    "EtaSqInteract":        "% --- eta^2 values ---",
    "DirMetricBLEUEntoX":   "% --- Per-direction per-metric means (Table 3) ---",
    "WilliamsMaxT":         "% --- Williams tests ---",
    "ZuluXcometPval":       "% --- Zulu xCOMET ---",
    "RuWmtOneRho":          "% --- Manual: year-stratified ---",
}

for key, data in stats.items():
    if key in SECTIONS:
        lines.append("")
        lines.append(SECTIONS[key])
    lines.append(
        rf"\newcommand{{\{key}}}{{{data['fmt']}}}  % {data['source']}"
    )

lines.append("")
with open(LATEX / "macros.tex", "w") as f:
    f.write("\n".join(lines) + "\n")
print(f"Wrote latex/macros.tex ({len(lines)} lines)")

# Summary of manual entries (flag for future automation)
manual_keys = [k for k, v in stats.items() if v["source"].startswith("manual")]
if manual_keys:
    print(f"\nManual entries ({len(manual_keys)}) — not yet sourced from a CSV:")
    for k in manual_keys:
        print(f"  {k}: {stats[k]['value']}  # {stats[k]['note']}")
