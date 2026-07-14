"""Abjad script mechanism validation: Hebrew vs. Pashto.

Both languages use abjad scripts (Hebrew: square script; Pashto: Nastaliq/Perso-Arabic).
The OOD hypothesis predicts:
  - Hebrew (he-en, WMT23): NOT in COMET-22 training → score compression
  - Pashto (ps-en, WMT20): IN COMET-22 training → no compression

If the compression is purely a script-type effect, both should show it.
If it is a training-data OOD effect, only Hebrew should show it.

This script computes the key statistics formally and outputs a comparison table
suitable for inclusion in the paper.

Run on the login node (no GPU needed):
  python scripts/analyze_abjad_mechanism.py --settings settings.toml
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

METRICS = ["comet", "cometkiwi", "cometkiwi23", "xcomet", "metricx", "bleu", "chrf", "bertscore"]
ABJAD_LANGS = ["he", "ps"]
CONTROL_LANGS = ["de", "zh", "es"]  # non-abjad, well-performing


def load_scores(results_dir: Path) -> dict[str, pd.DataFrame]:
    frames = {}
    for m in METRICS:
        p = results_dir / f"scores_{m}.csv"
        if p.exists():
            frames[m] = pd.read_csv(p)
    return frames


def cohen_d_quartile(scores: pd.Series) -> float:
    """Cohen's d between bottom and top quartile (discrimination measure)."""
    q1, q3 = scores.quantile(0.25), scores.quantile(0.75)
    bot, top = scores[scores <= q1], scores[scores >= q3]
    if len(bot) < 2 or len(top) < 2:
        return float("nan")
    pooled_sd = np.sqrt((bot.var() + top.var()) / 2)
    return float((top.mean() - bot.mean()) / pooled_sd) if pooled_sd > 0 else float("nan")


def main():
    project_root = Path(__file__).resolve().parent.parent
    results_dir = project_root / "results"

    score_frames = load_scores(results_dir)
    if "comet" not in score_frames:
        print("ERROR: scores_comet.csv not found", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # 1.  COMET score distribution comparison                              #
    # ------------------------------------------------------------------ #
    comet_df = score_frames["comet"]
    cross_mean = comet_df["comet"].mean()
    cross_std = comet_df["comet"].std()

    print("=" * 70)
    print("COMET-22 Score Distribution: Abjad Languages vs. Controls")
    print("=" * 70)
    print(f"Cross-language COMET mean: {cross_mean:.3f}  std: {cross_std:.3f}")
    print()
    print(f"{'Lang':<6} {'Script':<10} {'WCOS-22 in training?':<22} {'Mean':>6} {'Std':>6} {'z-score':>8} {'Cohen_d':>9}")
    print("-" * 70)

    script_info = {"he": ("abjad", "No — WMT23"), "ps": ("abjad", "Yes — WMT20"),
                   "de": ("alphabetic", "Yes"), "zh": ("logographic", "Yes"), "es": ("alphabetic", "Yes")}

    dist_rows = []
    for lang in ["he", "ps", "de", "zh", "es"]:
        c = comet_df[comet_df["lang"] == lang]["comet"].dropna()
        if len(c) == 0:
            continue
        z = (c.mean() - cross_mean) / cross_std
        d = cohen_d_quartile(c)
        script, in_train = script_info.get(lang, ("?", "?"))
        print(f"{lang:<6} {script:<10} {in_train:<22} {c.mean():>6.3f} {c.std():>6.3f} {z:>8.2f}σ {d:>9.2f}")
        dist_rows.append({"lang": lang, "script": script, "in_comet22_train": in_train,
                          "comet_mean": c.mean(), "comet_std": c.std(), "z_score": z, "cohens_d_quartile": d})

    # ------------------------------------------------------------------ #
    # 2.  Reference-free vs reference-based split                          #
    # ------------------------------------------------------------------ #
    print()
    print("=" * 70)
    print("Reference-free (QE) vs. Reference-based: Per-Language Spearman ρ")
    print("=" * 70)

    # Load quality scores from original sources
    # MQM languages (he, de, zh, es): from correlations.csv (already computed)
    # DA languages (ps): from WMT DA HuggingFace
    corr_df = pd.read_csv(results_dir / "correlations.csv")

    ref_based = ["comet", "xcomet", "metricx", "bleu", "chrf", "bertscore"]
    ref_free  = ["cometkiwi", "cometkiwi23"]

    rho_rows = []
    for lang in ABJAD_LANGS + CONTROL_LANGS:
        row = {"lang": lang}
        for m in METRICS:
            match = corr_df[(corr_df["lang"] == lang) & (corr_df["metric"] == m)]
            if match.empty:
                row[m] = float("nan")
            else:
                row[m] = float(match["spearman_r"].iloc[0])

        rb_vals = [row[m] for m in ref_based if not np.isnan(row.get(m, float("nan")))]
        rf_vals = [row[m] for m in ref_free  if not np.isnan(row.get(m, float("nan")))]
        row["mean_ref_based_rho"] = np.mean(rb_vals) if rb_vals else float("nan")
        row["mean_ref_free_rho"]  = np.mean(rf_vals) if rf_vals else float("nan")
        row["ref_free_advantage"] = row["mean_ref_free_rho"] - row["mean_ref_based_rho"]
        rho_rows.append(row)

    rho_df = pd.DataFrame(rho_rows)

    print(f"\n{'Lang':<6} {'COMET':>7} {'Kiwi22':>8} {'Kiwi23':>8} {'MetricX':>9} {'Ref-free Δ':>11}")
    print("-" * 52)
    for _, r in rho_df.iterrows():
        comet = r.get("comet", float("nan"))
        kiwi  = r.get("cometkiwi", float("nan"))
        kiwi23= r.get("cometkiwi23", float("nan"))
        mx    = r.get("metricx", float("nan"))
        adv   = r.get("ref_free_advantage", float("nan"))
        flag = " <-- QE WINS" if adv > 0.15 else ""
        print(f"{r['lang']:<6} {comet:>7.3f} {kiwi:>8.3f} {kiwi23:>8.3f} {mx:>9.3f} {adv:>11.3f}{flag}")

    # ------------------------------------------------------------------ #
    # 3.  Save outputs                                                     #
    # ------------------------------------------------------------------ #
    dist_df = pd.DataFrame(dist_rows)
    dist_df.to_csv(results_dir / "abjad_score_distributions.csv", index=False)
    rho_df.to_csv(results_dir / "abjad_metric_comparison.csv", index=False)

    print(f"\nSaved: results/abjad_score_distributions.csv")
    print(f"Saved: results/abjad_metric_comparison.csv")

    # ------------------------------------------------------------------ #
    # 4.  Interpretation                                                   #
    # ------------------------------------------------------------------ #
    print()
    print("=" * 70)
    print("Mechanism interpretation")
    print("=" * 70)
    he_row = rho_df[rho_df["lang"] == "he"]
    ps_row = rho_df[rho_df["lang"] == "ps"]
    if not he_row.empty and not ps_row.empty:
        he_adv = he_row["ref_free_advantage"].values[0]
        ps_adv = ps_row["ref_free_advantage"].values[0]
        print(f"  Hebrew (abjad, NOT in COMET-22 training): ref-free advantage = {he_adv:+.3f}")
        print(f"  Pashto (abjad, IN  COMET-22 training):   ref-free advantage = {ps_adv:+.3f}")
        print()
        if he_adv > 0.10 and abs(ps_adv) < 0.10:
            print("  VERDICT: OOD training data mechanism confirmed.")
            print("  Both languages share abjad script. Only Hebrew — which is OOD")
            print("  for COMET-22 — shows reference-free QE advantage.")
            print("  Pashto (in-distribution) shows parity: mechanism is not script-type alone.")
        else:
            print("  VERDICT: Pattern inconclusive — review distributions manually.")


if __name__ == "__main__":
    main()
