"""Recompute the direction×morphology table with correct direction labels.

The bug: fi, tr, et, lt, cs, ja were all labeled en_to_x in direction_analysis.csv,
but their data contains both X→en and en→X rows. This script:

  1. Loads per-language Spearman ρ from correlations.csv (correct for single-direction langs).
  2. Replaces fi/tr/et/lt/cs/ja with direction-separated ρ from direction_separated_correlations.csv.
  3. Recomputes cell means, CIs, η² for the direction×morphology table.
  4. Prints corrected macro values for macros.tex.

Run on login node:
  python scripts/recompute_dir_morph_table.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mqmbench.analysis.correlation import (
    MORPHOLOGY_TYPES, TRANSLATION_DIRECTIONS, RESOURCE_TIERS,
)

RESULTS = Path(__file__).resolve().parent.parent / "results"
METRICS = ["comet", "cometkiwi", "cometkiwi23", "xcomet", "metricx", "bleu", "chrf", "bertscore"]

# Languages confirmed to have mixed-direction data (both X→en and en→X pooled)
MIXED_LANGS = {"fi", "tr", "et", "lt", "cs", "ja",
               "kk", "ta", "ha", "pl", "is", "gu"}


def build_corrected_lang_dir_rho(metric: str) -> pd.DataFrame:
    """Return DataFrame with (lang, direction, morphology, spearman_r) for every language."""

    # --- Single-direction languages from correlations.csv ---
    corr = pd.read_csv(RESULTS / "correlations.csv")
    lang_to_dir = {lang: d for d, langs in TRANSLATION_DIRECTIONS.items() for lang in langs}
    lang_to_morph = {lang: m for m, langs in MORPHOLOGY_TYPES.items() for lang in langs}

    single_rows = []
    for lang, grp in corr[corr["metric"] == metric].groupby("lang"):
        if lang in MIXED_LANGS:
            continue  # replaced below
        direction = lang_to_dir.get(lang, "en_to_x")
        morph = lang_to_morph.get(lang, "fusional")
        rho = grp["spearman_r"].mean()  # mean across annotation tiers if multiple
        single_rows.append({"lang": lang, "direction": direction,
                             "morphology": morph, "spearman_r": rho})

    single_df = pd.DataFrame(single_rows)

    # --- Mixed-direction languages from direction_separated_correlations.csv ---
    sep_path = RESULTS / "direction_separated_correlations.csv"
    if not sep_path.exists():
        print(f"ERROR: {sep_path} not found — run analyze_direction_separated.py first.",
              file=sys.stderr)
        sys.exit(1)

    sep = pd.read_csv(sep_path)
    mixed_rows = []
    for (lang, direction), grp in sep[(sep["metric"] == metric) &
                                      (sep["lang"].isin(MIXED_LANGS))].groupby(["lang", "direction"]):
        morph = grp["morphology"].iloc[0]
        rho = grp["spearman_r"].mean()
        mixed_rows.append({"lang": f"{lang}_{direction[:3]}",  # e.g. fi_xto, fi_ent
                            "direction": direction, "morphology": morph, "spearman_r": rho})

    mixed_df = pd.DataFrame(mixed_rows)
    return pd.concat([single_df, mixed_df], ignore_index=True)


def cell_stats(rho_vals: list) -> dict:
    """Mean, bootstrap 95% CI over language-level ρ values."""
    if len(rho_vals) == 0:
        return {"mean": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"), "n": 0}
    mean_r = float(np.mean(rho_vals))
    if len(rho_vals) >= 3:
        rng = np.random.default_rng(42)
        boot = [float(np.mean(rng.choice(rho_vals, size=len(rho_vals), replace=True)))
                for _ in range(2000)]
        ci_lo = float(np.percentile(boot, 2.5))
        ci_hi = float(np.percentile(boot, 97.5))
    else:
        ci_lo = ci_hi = float("nan")
    return {"mean": mean_r, "ci_lo": ci_lo, "ci_hi": ci_hi, "n": len(rho_vals)}


def compute_eta_sq(df: pd.DataFrame) -> dict:
    """Simple η² for direction, morphology, interaction using per-language ρ."""
    y = df["spearman_r"].dropna().values
    if len(y) < 4:
        return {"dir": float("nan"), "morph": float("nan"), "interact": float("nan")}
    grand = y.mean()
    ss_total = ((y - grand) ** 2).sum()
    if ss_total == 0:
        return {"dir": 0.0, "morph": 0.0, "interact": 0.0}

    dir_means = df.groupby("direction")["spearman_r"].mean()
    morph_means = df.groupby("morphology")["spearman_r"].mean()
    ss_dir = sum((df["direction"] == d).sum() * (m - grand) ** 2 for d, m in dir_means.items())
    ss_morph = sum((df["morphology"] == mt).sum() * (m - grand) ** 2 for mt, m in morph_means.items())
    ss_interact = max(0.0, ss_total - ss_dir - ss_morph)
    return {
        "dir": float(ss_dir / ss_total),
        "morph": float(ss_morph / ss_total),
        "interact": float(ss_interact / ss_total),
    }


def main():
    print("=" * 70)
    print("Corrected Direction × Morphology Table (with direction-separated DA)")
    print("=" * 70)
    print()

    metric = "comet"
    df = build_corrected_lang_dir_rho(metric)

    # Filter to rows we actually want in the table (exclude pivot for main table)
    table_df = df[df["direction"].isin(["x_to_en", "en_to_x", "pivot"])].copy()

    print("Per-language ρ used in corrected table:")
    print(table_df[["lang", "direction", "morphology", "spearman_r"]]
          .sort_values(["direction", "morphology", "lang"]).to_string(index=False))
    print()

    # Cell stats
    print("=" * 70)
    print("Cell means (COMET Spearman ρ):")
    print("=" * 70)

    cells = {}
    for direction in ["x_to_en", "en_to_x", "pivot"]:
        for morph in ["isolating", "agglutinative", "fusional"]:
            cell_data = table_df[
                (table_df["direction"] == direction) &
                (table_df["morphology"] == morph)
            ]
            langs_in_cell = cell_data["lang"].tolist()
            rho_vals = cell_data["spearman_r"].dropna().tolist()
            stats = cell_stats(rho_vals)
            key = (direction, morph)
            cells[key] = stats
            if stats["n"] > 0:
                ci_str = f"[{stats['ci_lo']:.3f}, {stats['ci_hi']:.3f}]" if stats["n"] >= 3 else "[---]"
                print(f"  {direction} × {morph}: mean={stats['mean']:.3f} {ci_str} n={stats['n']}"
                      f"  langs={langs_in_cell}")

    # η²
    eta = compute_eta_sq(table_df[table_df["direction"].isin(["x_to_en", "en_to_x"])])
    print()
    print(f"  η²_dir={eta['dir']:.3f}  η²_morph={eta['morph']:.3f}  η²_interact={eta['interact']:.3f}")

    # Also print direction metric table (mean per direction, all metrics)
    print()
    print("=" * 70)
    print("Direction × Metric means (corrected):")
    print("=" * 70)

    for metric_name in ["bleu", "chrf", "comet", "xcomet", "metricx", "cometkiwi23"]:
        df_m = build_corrected_lang_dir_rho(metric_name)
        df_m = df_m[df_m["direction"].isin(["x_to_en", "en_to_x", "pivot"])]
        for direction in ["en_to_x", "x_to_en", "pivot"]:
            vals = df_m[df_m["direction"] == direction]["spearman_r"].dropna()
            if len(vals):
                print(f"  {metric_name} {direction}: mean={vals.mean():.3f}  n={len(vals)}")

    # ------------------------------------------------------------------ #
    # Print macro values for macros.tex                                    #
    # ------------------------------------------------------------------ #
    print()
    print("=" * 70)
    print("MACRO VALUES FOR macros.tex:")
    print("=" * 70)

    def fmt(v, digits=3):
        if np.isnan(v):
            return "---"
        return f"{v:.{digits}f}"

    # Direction×morphology cell macros (COMET)
    df_comet = build_corrected_lang_dir_rho("comet")
    df_comet = df_comet[df_comet["direction"].isin(["x_to_en", "en_to_x", "pivot"])]

    cell_data = {}
    for direction in ["x_to_en", "en_to_x", "pivot"]:
        for morph in ["isolating", "agglutinative", "fusional"]:
            cell = df_comet[(df_comet["direction"] == direction) & (df_comet["morphology"] == morph)]
            rho_vals = cell["spearman_r"].dropna().tolist()
            cell_data[(direction, morph)] = cell_stats(rho_vals)

    print(f"\\newcommand{{\\DirMorphCOMETXtoEnIsolating}}{{{fmt(cell_data[('x_to_en','isolating')]['mean'])}}}")
    print(f"\\newcommand{{\\DirMorphCOMETXtoEnAgglutin}}{{{fmt(cell_data[('x_to_en','agglutinative')]['mean'])}}}")
    print(f"\\newcommand{{\\DirMorphCOMETXtoEnFusional}}{{{fmt(cell_data[('x_to_en','fusional')]['mean'])}}}")
    print(f"\\newcommand{{\\DirMorphCOMETXtoEnFusionalCIlo}}{{{fmt(cell_data[('x_to_en','fusional')]['ci_lo'])}}}")
    print(f"\\newcommand{{\\DirMorphCOMETXtoEnFusionalCIhi}}{{{fmt(cell_data[('x_to_en','fusional')]['ci_hi'])}}}")
    print(f"\\newcommand{{\\DirMorphCOMETEntoXAgglutin}}{{{fmt(cell_data[('en_to_x','agglutinative')]['mean'])}}}")
    print(f"\\newcommand{{\\DirMorphCOMETEntoXAgglutinCIlo}}{{{fmt(cell_data[('en_to_x','agglutinative')]['ci_lo'])}}}")
    print(f"\\newcommand{{\\DirMorphCOMETEntoXAgglutinCIhi}}{{{fmt(cell_data[('en_to_x','agglutinative')]['ci_hi'])}}}")
    print(f"\\newcommand{{\\DirMorphCOMETEntoXFusional}}{{{fmt(cell_data[('en_to_x','fusional')]['mean'])}}}")
    print(f"\\newcommand{{\\DirMorphCOMETEntoXFusionalCIlo}}{{{fmt(cell_data[('en_to_x','fusional')]['ci_lo'])}}}")
    print(f"\\newcommand{{\\DirMorphCOMETEntoXFusionalCIhi}}{{{fmt(cell_data[('en_to_x','fusional')]['ci_hi'])}}}")
    print(f"\\newcommand{{\\DirMorphCOMETPivotFusional}}{{{fmt(cell_data[('pivot','fusional')]['mean'])}}}")
    print(f"\\newcommand{{\\DirMorphCOMETPivotFusionalCIlo}}{{{fmt(cell_data[('pivot','fusional')]['ci_lo'])}}}")
    print(f"\\newcommand{{\\DirMorphCOMETPivotFusionalCIhi}}{{{fmt(cell_data[('pivot','fusional')]['ci_hi'])}}}")
    print(f"\\newcommand{{\\EtaSqDir}}{{{fmt(eta['dir'])}}}")
    print(f"\\newcommand{{\\EtaSqMorph}}{{{fmt(eta['morph'])}}}")
    print(f"\\newcommand{{\\EtaSqInteract}}{{{fmt(eta['interact'])}}}")

    # Direction×metric table macros
    metric_map = {
        "bleu": "BLEU", "chrf": "ChrF", "comet": "COMET",
        "xcomet": "xCOMET", "metricx": "MetricX",
    }
    for metric_name, label in metric_map.items():
        df_m = build_corrected_lang_dir_rho(metric_name)
        df_m = df_m[df_m["direction"].isin(["x_to_en", "en_to_x", "pivot"])]
        for direction, dir_label in [("en_to_x", "EntoX"), ("x_to_en", "XtoEn"), ("pivot", "Pivot")]:
            vals = df_m[df_m["direction"] == direction]["spearman_r"].dropna()
            v = vals.mean() if len(vals) else float("nan")
            print(f"\\newcommand{{\\DirMetric{label}{dir_label}}}{{{fmt(v)}}}")


if __name__ == "__main__":
    main()
