"""Generate presentation-quality figures from correlations.csv.

Run from the project root:
    python scripts/make_presentation_plots.py

Outputs to results/plots/presentation_*.png
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import seaborn as sns

RESULTS = Path("results")
OUT = RESULTS / "plots"
OUT.mkdir(parents=True, exist_ok=True)


def paper_stat(key: str) -> str:
    """Read a formatted value from the JSON SSOT (results/paper_stats.json),
    for figure annotations that state a derived statistic. Prevents the
    hardcoded-number-in-a-plot-title failure mode found in the now-removed
    plot_score_discrimination() (its Cohen's d annotation; see
    generate_paper_stats.py's docstring) -- a number baked into an image can't be caught by
    assert_paper_invariants.py the way a LaTeX macro reference can, so this
    is the only thing standing between the figure and drift."""
    with open(RESULTS / "paper_stats.json") as f:
        stats = json.load(f)
    return stats[key]["fmt"]

plt.rcParams.update({
    "font.size": 15,
    "axes.titlesize": 17,
    "axes.labelsize": 15,
    "xtick.labelsize": 13,
    "ytick.labelsize": 13,
    "legend.fontsize": 13,
    "figure.dpi": 150,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

METRIC_LABELS = {
    "bleu":        "BLEU",
    "chrf":        "ChrF",
    "bertscore":   "BERTScore",
    "bleurt":      "BLEURT",
    "comet":       "COMET",
    "xcomet":      "xCOMET",
    "metricx":     "MetricX-24",
    "cometkiwi":   "COMET-Kiwi",
    "cometkiwi23": "COMET-Kiwi-23",
    "gemba":       "GEMBA",
}

ALL_METRICS = ["bleu", "chrf", "bertscore", "bleurt", "comet", "xcomet",
               "metricx", "cometkiwi", "cometkiwi23", "gemba"]

TIER_COLORS = {
    "high":   "#2166ac",
    "medium": "#4dac26",
    "low":    "#d01c8b",
}

TIER_ORDER = ["high", "medium", "low"]


def load_corr():
    path = RESULTS / "correlations.csv"
    if not path.exists():
        sys.exit(f"correlations.csv not found at {path}")
    df = pd.read_csv(path)
    df["metric_label"] = df["metric"].map(lambda m: METRIC_LABELS.get(m, m.upper()))
    return df


# ---------------------------------------------------------------------------
# Figure 1: Spearman r by metric and resource tier (grouped bar)
# ---------------------------------------------------------------------------
#: Mirrors generate_paper_stats.py's METRIC_KEY/TIER_KEY exactly, so the macro
#: names constructed here (e.g. TierCOMETHighRho) hit the same JSON entries
#: Table 1 and the prose read from.
_TIER_STAT_METRIC_KEY = {
    "bleu": "BLEU", "chrf": "ChrF", "bertscore": "BERTScore",
    "bleurt": "BLEURT", "comet": "COMET", "xcomet": "xCOMET",
    "metricx": "MetricX", "cometkiwi": "KiwiXXII", "cometkiwi23": "KiwiXXIII",
    "gemba": "GEMBA",
}
_TIER_STAT_TIER_KEY = {"high": "High", "medium": "Med", "low": "Low"}


def plot_tier_bar(df: pd.DataFrame):
    # Do NOT recompute tier means from raw per-language correlations.csv here:
    # that averages per-language (weighting the medium tier toward its 6 DA
    # languages over the 1 MQM en-es language), while generate_paper_stats.py
    # averages per-annotation-tier via tier_summary.csv (equal weight between
    # the DA group and the es-MQM group). The two methodologies can and did
    # disagree on ordering for xCOMET. Read the SSOT values instead so this
    # figure can never silently diverge from Table 1 / the prose again.
    with open(RESULTS / "paper_stats.json") as f:
        stats = json.load(f)

    metrics = [m for m in ALL_METRICS if m in df["metric"].unique()]

    def tier_val(metric, tier):
        mk = _TIER_STAT_METRIC_KEY.get(metric)
        tk = _TIER_STAT_TIER_KEY.get(tier)
        key = f"Tier{mk}{tk}Rho"
        return stats[key]["value"] if key in stats else np.nan

    # Designed for \textwidth ≈ 6.75" (figure* spanning both columns).
    fig, ax = plt.subplots(figsize=(13.5, 4.5))
    x = np.arange(len(metrics))
    width = 0.25
    offsets = [-width, 0, width]

    ax.grid(axis="y", linestyle=":", linewidth=0.7, color="#999", alpha=0.6, zorder=0)
    ax.set_axisbelow(True)

    for i, tier in enumerate(TIER_ORDER):
        vals = [tier_val(m, tier) for m in metrics]
        ax.bar(x + offsets[i], vals, width, label=tier.capitalize(),
               color=TIER_COLORS[tier], alpha=0.88, edgecolor="white", linewidth=0.5, zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels([METRIC_LABELS.get(m, m.upper()) for m in metrics],
                       rotation=30, ha="right", fontsize=13)
    ax.set_ylabel("Spearman $r$ (avg. per resource tier)", fontsize=13)
    ax.set_title("MT Metric Correlation with Human Judgment by Resource Tier", fontsize=15)
    ax.set_ylim(-0.05, 1.0)
    ax.axhline(0, color="black", linewidth=0.7, linestyle="--")
    ax.legend(title="Resource tier", frameon=False, fontsize=12, title_fontsize=12)

    plt.tight_layout()
    path = OUT / "presentation_tier_bar.pdf"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")


# ---------------------------------------------------------------------------
# Teaser figure: direction dominates morphological type
# ---------------------------------------------------------------------------
def plot_direction_morphology_teaser():
    """Grouped bar chart of the paper's headline finding: en->X vs. X->en
    COMET Spearman rho, split by morphological type. Reads the exact cell
    means/CIs used by Table 2 directly from results/paper_stats.json (the
    DirMorphCOMET* keys generate_paper_stats.py writes) rather than
    recomputing anything independently, so this figure can never silently
    diverge from the table it illustrates. Designed as a single-column,
    page-1 "teaser" figure -- compact enough to sit near the abstract.
    """
    with open(RESULTS / "paper_stats.json") as f:
        stats = json.load(f)

    def val(key):
        return stats[key]["value"] if key in stats else None

    def ci(key):
        lo, hi = stats.get(f"{key}CIlo"), stats.get(f"{key}CIhi")
        if lo is None or hi is None:
            return None
        return (val(key) - lo["value"], hi["value"] - val(key))

    # Isolating excluded: there are no Tier-1 en->X isolating observations
    # (see Limitations), so it can't show the direction contrast this figure
    # exists to make -- noted in the caption instead of drawn as an empty bar.
    morphs = ["agglutinative", "fusional"]
    labels = ["Agglutinative", "Fusional"]
    entox_keys = {"agglutinative": "DirMorphCOMETEntoXAgglutin",
                  "fusional": "DirMorphCOMETEntoXFusional"}
    xtoen_keys = {"agglutinative": "DirMorphCOMETXtoEnAgglutin",
                  "fusional": "DirMorphCOMETXtoEnFusional"}

    entox_vals = [val(entox_keys[m]) for m in morphs]
    xtoen_vals = [val(xtoen_keys[m]) for m in morphs]
    entox_err = [ci(entox_keys[m]) for m in morphs]
    xtoen_err = [ci(xtoen_keys[m]) for m in morphs]

    def err_array(errs):
        lo = [e[0] if e else 0 for e in errs]
        hi = [e[1] if e else 0 for e in errs]
        return [lo, hi]

    # Two shades of the same hue (dark/light green) rather than two distinct
    # colors: en->X and X->en are the same underlying metric (COMET) split by
    # direction, not two different conditions the way resource tiers are.
    ENTOX_COLOR, XTOEN_COLOR = "#1b7837", "#a6dba0"

    fig, ax = plt.subplots(figsize=(6.75, 4.2))
    x = np.arange(len(morphs))
    width = 0.32

    bars_entox = ax.bar(x - width / 2, entox_vals, width, label="en$\\to$X",
           color=ENTOX_COLOR, alpha=0.9, edgecolor="white", linewidth=0.5, zorder=3,
           yerr=err_array(entox_err), capsize=4, error_kw=dict(lw=1.2, zorder=4))
    bars_xtoen = ax.bar(x + width / 2, xtoen_vals, width, label="X$\\to$en",
           color=XTOEN_COLOR, alpha=0.9, edgecolor="white", linewidth=0.5, zorder=3,
           yerr=err_array(xtoen_err), capsize=4, error_kw=dict(lw=1.2, zorder=4))

    # Value labels directly on each bar: lets a reader read exact rho at a
    # glance without cross-referencing Table 2.
    # The light-green X->en bars are too pale for white text to stay legible.
    for bars, vals, label_color in [(bars_entox, entox_vals, "white"),
                                      (bars_xtoen, xtoen_vals, "#1b7837")]:
        for bar, v in zip(bars, vals):
            if np.isnan(v):
                continue
            ax.text(bar.get_x() + bar.get_width() / 2, 0.025, f"{v:.2f}",
                    ha="center", va="bottom", fontsize=9.5, color=label_color,
                    fontweight="bold", zorder=5)

    # Gap brackets: the headline finding IS the en->X vs. X->en gap, not the
    # raw bar heights, so draw it directly rather than making the reader
    # subtract two bars mentally. Reuses the same GapDirAgglutin/GapDirFusional
    # SSOT macros already cited in the discussion prose (no separate number).
    _light_gray = "#888"
    for xi, morph in enumerate(morphs):
        top = max(entox_vals[xi], xtoen_vals[xi]) + (entox_err[xi][1] if entox_err[xi] else 0) + 0.05
        gap_key = "GapDirAgglutin" if morph == "agglutinative" else "GapDirFusional"
        ax.annotate(
            "", xy=(xi - width / 2, top), xytext=(xi + width / 2, top),
            arrowprops=dict(arrowstyle="-", color=_light_gray, lw=1.1,
                             shrinkA=0, shrinkB=0,
                             connectionstyle="bar,fraction=0.15"),
        )
        ax.text(xi, top + 0.075, f"+{paper_stat(gap_key)}", ha="center", va="bottom",
                fontsize=10, color=_light_gray, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=12)
    ax.set_ylabel("COMET Spearman $\\rho$", fontsize=12)
    ax.set_ylim(0, 1.15)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_title("Direction Matters More Than Morphology for Metric Reliability", fontsize=13)
    ax.legend(frameon=False, fontsize=11, loc="upper left")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    path = OUT / "presentation_direction_morphology_teaser.pdf"
    plt.savefig(path, bbox_inches="tight")
    plt.savefig(str(path).replace(".pdf", ".png"), bbox_inches="tight", dpi=150)
    plt.close()
    print(f"Saved {path}")


# ---------------------------------------------------------------------------
# Figure 2: Per-language Spearman heatmap
# ---------------------------------------------------------------------------
# The 12 languages with data in BOTH translation directions. correlations.csv
# (this function's main input) stores ONE row per (lang, metric) for these --
# a POOLED value silently averaging over both directions -- not the
# direction-specific value the rest of the paper's direction analysis uses.
# Found 2026-09-12 (advisor + independent review, same day): this pooled
# value doesn't match Table 8's direction-separated per-language values (e.g.
# kk-en COMET 0.519 vs. this row's pooled 0.613), even though Table 2's
# headline agglutinative-X-to-en cell mean is built from Table 8's correct
# per-direction value. Table 7 (tab:direction_full) now shows each of these
# languages' value for whichever direction section it's placed under, using
# direction_separated_correlations.csv; this heatmap must match that choice
# language-for-language, or the two "same language, same metric" numbers in
# the paper would disagree again.
MIXED_LANG_DISPLAY_DIRECTION = {
    "fi": "en_to_x", "tr": "en_to_x", "et": "en_to_x", "lt": "en_to_x",
    "cs": "en_to_x", "ja": "en_to_x", "ta": "en_to_x", "ha": "en_to_x",
    "pl": "en_to_x", "is": "en_to_x", "kk": "x_to_en", "gu": "x_to_en",
}


def _direction_disambiguated_corr(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with MIXED_LANG_DISPLAY_DIRECTION languages'
    pooled rows replaced by their direction-specific rows (same direction
    Table 7 shows them under), for every metric direction_separated_
    correlations.csv covers. Non-metric columns (resource_tier etc.) are
    carried over unchanged from the original pooled row for that language,
    since those don't vary by direction."""
    sep_path = RESULTS / "direction_separated_correlations.csv"
    if not sep_path.exists() or not MIXED_LANG_DISPLAY_DIRECTION:
        return df
    sep = pd.read_csv(sep_path)
    out_parts = [df[~df["lang"].isin(MIXED_LANG_DISPLAY_DIRECTION)]]
    for lang, direction in MIXED_LANG_DISPLAY_DIRECTION.items():
        orig_rows = df[df["lang"] == lang]
        if orig_rows.empty:
            continue
        meta_cols = [c for c in df.columns if c not in ("metric", "spearman_r", "n", "lang")]
        meta = orig_rows.iloc[0][meta_cols].to_dict()
        sub = sep[(sep["lang"] == lang) & (sep["direction"] == direction)][["metric", "spearman_r", "n"]].copy()
        if sub.empty:
            out_parts.append(orig_rows)
            continue
        sub["lang"] = lang
        for k, v in meta.items():
            sub[k] = v
        out_parts.append(sub[df.columns])
    return pd.concat(out_parts, ignore_index=True)


def plot_language_heatmap(df: pd.DataFrame):
    metrics = [m for m in ALL_METRICS if m in df["metric"].unique()]

    pivot = df.pivot_table(
        index="lang", columns="metric", values="spearman_r", aggfunc="mean"
    )[metrics]

    # Sort languages by resource tier then spearman_r of best metric
    lang_meta = df[["lang", "resource_tier"]].drop_duplicates().set_index("lang")
    tier_rank = {"high": 0, "medium": 1, "low": 2}
    pivot = pivot.copy()
    pivot["_tier"] = pivot.index.map(lambda l: tier_rank.get(lang_meta.loc[l, "resource_tier"] if l in lang_meta.index else "low", 2))
    pivot = pivot.sort_values(["_tier", metrics[-1]], ascending=[True, False]).drop(columns="_tier")

    col_labels = [METRIC_LABELS.get(m, m.upper()) for m in pivot.columns]

    # Designed for \textwidth ≈ 6.75" (figure* spanning both columns).
    fig, ax = plt.subplots(figsize=(13.5, 8))
    sns.heatmap(
        pivot, annot=True, fmt=".2f", cmap="RdYlGn",
        center=0, vmin=-0.2, vmax=0.9,
        linewidths=0.3, linecolor="white",
        xticklabels=col_labels,
        ax=ax, cbar_kws={"label": "Spearman r", "shrink": 0.7},
        annot_kws={"size": 9},
    )
    ax.set_title("Metric–Human Correlation per Language", pad=10, fontsize=15)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.tick_params(axis="x", labelsize=12, rotation=30)
    ax.tick_params(axis="y", labelsize=11)

    # Align x-tick labels to the right after rotation
    for lbl in ax.get_xticklabels():
        lbl.set_ha("right")

    # Tier divider lines
    langs = list(pivot.index)
    tier_boundaries = []
    prev_tier = lang_meta.loc[langs[0], "resource_tier"] if langs[0] in lang_meta.index else "unknown"
    for i, lang in enumerate(langs[1:], 1):
        t = lang_meta.loc[lang, "resource_tier"] if lang in lang_meta.index else "unknown"
        if t != prev_tier:
            tier_boundaries.append(i)
            prev_tier = t
    for b in tier_boundaries:
        ax.axhline(b, color="black", linewidth=1.5)

    # Mark the Ukrainian outlier by colouring its y-tick label red.
    # A text-box annotation overlaps cell values at this figure size;
    # the caption already explains the domain-outlier status.
    if "uk" in langs:
        uk_idx = langs.index("uk")
        for tick in ax.get_yticklabels():
            if tick.get_text().strip() == "uk":
                tick.set_color("#c0392b")
                tick.set_fontweight("bold")

    plt.tight_layout()
    path = OUT / "presentation_language_heatmap.pdf"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")


# ---------------------------------------------------------------------------
# Figure 3: Data pipeline diagram (text-based, no data needed)
# ---------------------------------------------------------------------------
def plot_pipeline_diagram():
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 4)
    ax.axis("off")

    tiers = [
        ("Tier 1a\nWMT MQM", 1.5, "#2166ac",
         "de · zh · ru · he · es\nProfessional MQM annotations\n(span-level errors)"),
        ("Tier 1b\nWMT DA", 5.0, "#4dac26",
         "cs · tr · uk · ha · km · ps\nDirect Assessment scores\n(sentence-level)"),
        ("Tier 2\nSynthetic MQM", 8.5, "#d01c8b",
         "sw · ht · lo\nFLORES+ → NLLB-200 → Llama-3.1-8B\n(GEMBA-MQM style)"),
    ]

    for label, x, color, detail in tiers:
        # Box
        rect = mpatches.FancyBboxPatch((x - 1.3, 1.6), 2.6, 1.8,
            boxstyle="round,pad=0.15", linewidth=2,
            edgecolor=color, facecolor=color + "22")
        ax.add_patch(rect)
        ax.text(x, 2.85, label, ha="center", va="center",
                fontsize=13, fontweight="bold", color=color)
        ax.text(x, 2.0, detail, ha="center", va="center",
                fontsize=9.5, color="#333333", linespacing=1.5)

    # Arrow down to metrics
    for x in [1.5, 5.0, 8.5]:
        ax.annotate("", xy=(x, 1.55), xytext=(x, 1.3),
                    arrowprops=dict(arrowstyle="->", color="#555", lw=1.5))

    ax.text(5.0, 0.9, "BLEU · ChrF · BERTScore · COMET · COMET-Kiwi",
            ha="center", va="center", fontsize=13,
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#f0f0f0", edgecolor="#888"))
    ax.text(5.0, 0.35, "Spearman / Kendall / SPA  ·  Bootstrap 95% CIs  ·  Williams test",
            ha="center", va="center", fontsize=10.5, color="#555555")

    ax.set_title(
        f"Three-Tier Annotation Design — {paper_stat('NumLanguages')} Languages, "
        f"{paper_stat('NumLanguageFamilies')} Families, {paper_stat('NumScriptTypes')} Script Types",
        fontsize=14, pad=8)

    plt.tight_layout()
    path = OUT / "presentation_pipeline.pdf"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")


# ---------------------------------------------------------------------------
# Figure 4: COMET-Kiwi vs. COMET scatter by resource tier
# ---------------------------------------------------------------------------
def plot_kiwi_comparison(df: pd.DataFrame):
    """Scatter: COMET-Kiwi Spearman r (y) vs. COMET Spearman r (x), per language."""
    if "comet" not in df["metric"].unique() or "cometkiwi" not in df["metric"].unique():
        print("Skipping Figure 4: cometkiwi not in correlations.csv")
        return

    comet_df = df[df["metric"] == "comet"][["lang", "resource_tier", "spearman_r", "spa"]].rename(
        columns={"spearman_r": "comet_r", "spa": "comet_spa"})
    kiwi_df = df[df["metric"] == "cometkiwi"][["lang", "spearman_r", "spa"]].rename(
        columns={"spearman_r": "kiwi_r", "spa": "kiwi_spa"})
    merged = comet_df.merge(kiwi_df, on="lang").dropna(subset=["comet_r", "kiwi_r"])

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

    for ax, (cx, ky, xlabel, ylabel, title) in zip(axes, [
        ("comet_r", "kiwi_r",   "COMET (ref-based) Spearman r",   "COMET-Kiwi (ref-free) Spearman r",   "Spearman r"),
        ("comet_spa", "kiwi_spa", "COMET (ref-based) SPA",          "COMET-Kiwi (ref-free) SPA",          "Soft Pairwise Accuracy"),
    ]):
        if cx not in merged.columns or ky not in merged.columns:
            continue
        for tier in TIER_ORDER:
            sub = merged[merged["resource_tier"] == tier]
            if sub.empty:
                continue
            ax.scatter(sub[cx], sub[ky], label=tier.capitalize(),
                       color=TIER_COLORS[tier], s=65, alpha=0.88, zorder=3)
            for _, row in sub.iterrows():
                ax.annotate(row["lang"].upper(), (row[cx], row[ky]),
                            fontsize=7, ha="center", va="bottom",
                            color=TIER_COLORS[tier])

        all_v = pd.concat([merged[cx], merged[ky]]).dropna()
        lo, hi = all_v.min() - 0.03, all_v.max() + 0.03
        ax.plot([lo, hi], [lo, hi], "k--", lw=0.8, alpha=0.5, label="Equal performance")
        ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
        ax.set_xlabel(xlabel, fontsize=13)
        ax.set_ylabel(ylabel, fontsize=13)
        ax.set_title(f"Reference-free vs. Reference-based\n{title}", fontsize=14)
        ax.legend(title="Resource tier", frameon=False, fontsize=10)

    plt.suptitle("COMET-Kiwi vs. COMET: Does Dropping the Reference Help Low-resource Pairs?",
                 fontsize=13, y=1.01)
    plt.tight_layout()
    path = OUT / "presentation_kiwi_vs_comet.pdf"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")


# ---------------------------------------------------------------------------
# Figure 5: Medium > High anomaly — per-year variance decomposition
# ---------------------------------------------------------------------------
def plot_anomaly(df: pd.DataFrame):
    """Load tier_anomaly.csv and produce the variance-decomposition figure."""
    path = RESULTS / "tier_anomaly.csv"
    if not path.exists():
        print("Skipping Figure 5: tier_anomaly.csv not found (run pipeline first)")
        return

    anomaly_df = pd.read_csv(path)
    comet_df = anomaly_df[anomaly_df["metric"] == "comet"].copy()
    multi = comet_df[comet_df["year"] != "unknown"]
    if multi.empty:
        print("Skipping Figure 5: no multi-year data in tier_anomaly.csv")
        return

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Left: per-year Spearman r lines for high-resource languages
    ax = axes[0]
    for lang in sorted(multi[multi["resource_tier"] == "high"]["lang"].unique()):
        sub = multi[(multi["lang"] == lang) & (multi["resource_tier"] == "high")].sort_values("year")
        if sub["year"].nunique() < 2:
            continue
        ax.plot(sub["year"].astype(str), sub["year_spearman_r"],
                marker="o", label=lang.upper(), linewidth=2)
    ax.set_title("Per-year COMET Spearman r\n(high-resource languages)", fontsize=14)
    ax.set_xlabel("WMT Year")
    ax.set_ylabel("COMET Spearman r")
    ax.legend(frameon=False, fontsize=10)

    # Right: mean vs. std scatter coloured by tier
    ax = axes[1]
    var_df = (
        multi.groupby(["lang", "resource_tier"])["year_spearman_r"]
        .agg(mean_r="mean", std_r="std")
        .reset_index()
        .dropna(subset=["std_r"])
    )
    for tier in TIER_ORDER:
        sub = var_df[var_df["resource_tier"] == tier]
        if sub.empty:
            continue
        ax.scatter(sub["mean_r"], sub["std_r"], label=tier.capitalize(),
                   color=TIER_COLORS[tier], s=65, alpha=0.88)
        for _, row in sub.iterrows():
            ax.annotate(row["lang"].upper(), (row["mean_r"], row["std_r"]),
                        fontsize=7, ha="center", va="bottom",
                        color=TIER_COLORS[tier])
    ax.set_xlabel("Mean per-year COMET Spearman r", fontsize=13)
    ax.set_ylabel("Std dev across WMT years (heterogeneity)", fontsize=13)
    ax.set_title("Cross-year Variance Explains the Anomaly\n"
                 "(high std = aggregate correlation is depressed)", fontsize=14)
    ax.legend(frameon=False, fontsize=10)

    plt.suptitle("Why Medium-resource Languages Outperform High-resource Ones",
                 fontsize=13, y=1.01)
    plt.tight_layout()
    path = OUT / "presentation_tier_anomaly.pdf"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")


def plot_kiwi23_vs_comet(df: pd.DataFrame):
    """Single-panel scatter: Kiwi-23 (y) vs COMET (x), all languages.

    General reference-free-vs-reference-based comparison; no single language
    is singled out (a Hebrew-specific out-of-distribution annotation was
    removed after the underlying finding was retracted -- see research log,
    2026-09-11).
    """
    if "comet" not in df["metric"].unique() or "cometkiwi23" not in df["metric"].unique():
        print("Skipping kiwi23_vs_comet: cometkiwi23 not in correlations.csv")
        return

    comet_df = df[df["metric"] == "comet"][["lang", "resource_tier", "spearman_r"]].rename(
        columns={"spearman_r": "comet_r"})
    kiwi_df = df[df["metric"] == "cometkiwi23"][["lang", "spearman_r"]].rename(
        columns={"spearman_r": "kiwi23_r"})
    merged = comet_df.merge(kiwi_df, on="lang").dropna(subset=["comet_r", "kiwi23_r"])

    # Designed for \textwidth ≈ 6.75" (figure* spanning both columns).
    fig, ax = plt.subplots(figsize=(13.5, 6.5))

    from adjustText import adjust_text

    texts = []
    for tier in TIER_ORDER:
        sub = merged[merged["resource_tier"] == tier]
        if sub.empty:
            continue
        ax.scatter(sub["comet_r"], sub["kiwi23_r"], label=tier.capitalize(),
                   color=TIER_COLORS[tier], s=100, alpha=0.88, zorder=3)
        for _, row in sub.iterrows():
            lang = row["lang"].upper()
            t = ax.text(row["comet_r"], row["kiwi23_r"], lang,
                        fontsize=10, color=TIER_COLORS[tier])
            texts.append(t)

    all_v = pd.concat([merged["comet_r"], merged["kiwi23_r"]]).dropna()
    lo, hi = all_v.min() - 0.04, all_v.max() + 0.04
    ax.plot([lo, hi], [lo, hi], "k--", lw=0.9, alpha=0.45, label="Equal performance")

    adjust_text(texts, ax=ax,
                arrowprops=dict(arrowstyle="-", color="gray", lw=0.5),
                expand=(1.3, 1.5), force_text=(0.3, 0.5),
                min_arrow_len=4)

    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("COMET (reference-based) Spearman $r$", fontsize=13)
    ax.set_ylabel("COMET-Kiwi-23 (reference-free) Spearman $r$", fontsize=13)
    ax.set_title("Reference-free QE vs. Reference-based COMET", fontsize=15)
    ax.legend(title="Resource tier", frameon=False, fontsize=11, title_fontsize=11)
    ax.tick_params(labelsize=11)

    plt.tight_layout()
    path = OUT / "presentation_kiwi23_vs_comet.pdf"
    plt.savefig(path, bbox_inches="tight")
    plt.savefig(str(path).replace(".pdf", ".png"), bbox_inches="tight", dpi=150)
    plt.close()
    print(f"Saved {path}")


FEAT_LABELS = {
    "resource_tier=high":         "High-resource tier",
    "resource_tier=medium":       "Medium-resource tier",
    "resource_tier=low":          "Low-resource tier",
    "script_type=abjad":          "Abjad script",
    "script_type=abugida":        "Abugida script",
    "script_type=logographic":    "Logographic script",
    "morphology_type=agglutinative": "Agglutinative",
    "morphology_type=isolating":  "Isolating",
    "direction=pivot":            "Pivot direction",
    "direction=x_to_en":          "→ English direction",
    "word_order=1":               "SOV word order",
    "word_order=7":               "Free word order",
    "word_segmentation":          "No word spaces",
    "num_cases":                  "Case count",
    "affix_direc":                "Affix directionality",
}

_FOCAL_METRICS = ["comet", "metricx", "cometkiwi", "cometkiwi23"]


def plot_ridge_coefficients():
    """2×2 horizontal bar charts: top-6 Ridge coefficients for 4 focal metrics."""
    coef_path = RESULTS / "predictor" / "coefficients.csv"
    if not coef_path.exists():
        print("Skipping ridge coefficients: results/predictor/coefficients.csv not found")
        return

    coef_df = pd.read_csv(coef_path)
    coef_df["coefficient"] = coef_df["coefficient"].astype(float)

    fig, axes = plt.subplots(2, 2, figsize=(13.5, 9))
    axes = axes.flatten()

    pos_color = "#2166ac"
    neg_color = "#d6604d"

    for ax, metric in zip(axes, _FOCAL_METRICS):
        sub = coef_df[coef_df["metric"] == metric].copy()
        sub = sub.reindex(sub["coefficient"].abs().sort_values(ascending=False).index)
        sub = sub.head(6).sort_values("coefficient")

        labels = [FEAT_LABELS.get(f, f) for f in sub["feature"]]
        vals = sub["coefficient"].tolist()
        colors = [pos_color if v >= 0 else neg_color for v in vals]

        bars = ax.barh(labels, vals, color=colors, alpha=0.85, edgecolor="white", linewidth=0.5)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_title(METRIC_LABELS.get(metric, metric.upper()), fontsize=14, fontweight="bold")
        ax.set_xlabel("Standardized coefficient", fontsize=11)
        ax.tick_params(axis="y", labelsize=10)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # Value labels inside each bar (avoids overlap with feature label text)
        for bar, v in zip(bars, vals):
            if abs(v) < 0.002:
                continue
            xpos = v / 2  # midpoint of bar
            ax.text(xpos, bar.get_y() + bar.get_height() / 2,
                    f"{v:+.3f}", va="center", ha="center", fontsize=8,
                    color="white", fontweight="bold")

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=pos_color, alpha=0.85, label="Increases advantage over BLEU"),
        Patch(facecolor=neg_color, alpha=0.85, label="Decreases advantage over BLEU"),
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=2,
               fontsize=11, frameon=False, bbox_to_anchor=(0.5, -0.02))

    fig.suptitle("Top Typological Predictors of Metric Advantage over BLEU\n"
                 "(Ridge regression, LOLO-CV, standardized coefficients)",
                 fontsize=14, y=1.01)
    plt.tight_layout()
    path = OUT / "presentation_ridge_coefficients.pdf"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")



if __name__ == "__main__":
    plot_pipeline_diagram()   # no data needed
    plot_direction_morphology_teaser()  # reads paper_stats.json only
    df = load_corr()
    df_disambig = _direction_disambiguated_corr(df)  # see comment above MIXED_LANG_DISPLAY_DIRECTION
    # Tier 2 (synthetic_mqm) languages use LLM-generated, not human, quality
    # judgments -- excluded here because both kiwi-comparison figures'
    # captions specifically claim "all N languages WITH HUMAN ANNOTATIONS"
    # (found silently including all 33 languages, caption said 26, 2026-09-12).
    df_human = df_disambig[df_disambig["annotation_tier"] != "synthetic_mqm"]
    plot_tier_bar(df)
    plot_language_heatmap(df_disambig)
    plot_kiwi_comparison(df_human)
    plot_kiwi23_vs_comet(df_human)
    plot_ridge_coefficients()
    plot_anomaly(df)          # reads tier_anomaly.csv separately
    print("Done. Files in results/plots/")
