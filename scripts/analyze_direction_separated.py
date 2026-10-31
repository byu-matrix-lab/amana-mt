"""Direction-separated correlation analysis with LOO validation and bootstrap CIs.

Expanded from 6 to 15 languages (all WMT DA languages with English on one side).
Adds:
  - Leave-one-out (LOO) cross-validation per cell: predicts winner from N-1 langs,
    checks against held-out lang. Reports LOO accuracy per (direction, morphology) cell.
  - Bootstrap winner-fraction CIs: resamples languages within each cell 1000x,
    reports 95% CI on the fraction of bootstrap samples where CK23 beats COMET.

Language coverage (15 languages, all metric scores pre-computed):
  Agglutinative (X→en + en→X): fi, tr, et, ja, kk, ta
  Fusional      (X→en + en→X): cs, lt, pl, is, gu, ha [en→X only: lv]
  Fusional      (X→en only):    ps
  Isolating     (X→en only):    km

  Morphology labels are derived from MORPHOLOGY_TYPES (correlation.py), not
  hardcoded here (see MORPHOLOGY below). Hausa's classification there is
  fusional: its Afroasiatic verbal-grade system (tone/vowel apophony fusing
  aspect, transitivity, and direction into one form) is fusional-type
  behavior, even though it also has real agglutinative affixation — a
  documented case of genuinely mixed typology.

Run on login node (no GPU needed):
  cd /path/to/project && python scripts/analyze_direction_separated.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mqmbench.data.wmt_da import load_wmt_da
from mqmbench.analysis.correlation import MORPHOLOGY_TYPES

RESULTS = Path(__file__).resolve().parent.parent / "results"

METRICS = ["comet", "cometkiwi", "cometkiwi23", "xcomet", "metricx",
           "bleu", "chrf", "bertscore", "bleurt"]

KEY_METRICS = ["comet", "cometkiwi23", "metricx"]

# All WMT DA languages with English on one side (excluding MQM Tier 1a de/ru/zh
# and domain-confounded uk, and non-English pivot pairs).
ALL_LANGS = ["fi", "tr", "et", "lt", "cs", "ja",   # original 6
             "kk", "ta", "ha",                       # new agglutinative/fusional
             "pl", "is", "gu", "lv",                 # new fusional
             "km", "ps"]                             # new isolating + fusional X-only

# Derived from the single canonical MORPHOLOGY_TYPES dict (correlation.py) —
# not hand-maintained here. A prior version of this file hardcoded its own
# copy of this mapping and drifted from the canonical one for Hausa (listed
# agglutinative here, fusional in MORPHOLOGY_TYPES), producing inconsistent
# morphology labels across tables that a reviewer had to catch. Deriving
# from one source makes that class of bug structurally impossible.
_LANG_TO_MORPH = {lang: mtype for mtype, langs in MORPHOLOGY_TYPES.items() for lang in langs}
MORPHOLOGY = {lang: _LANG_TO_MORPH[lang] for lang in ALL_LANGS}

# Lookup table predictions — best metric per (morphology, direction) cell.
# Updated to reflect paper claims: CK23 for agglutinative (any) and fusional X→en.
LOOKUP_TABLE = {
    ("agglutinative", "x_to_en"): "cometkiwi23",
    ("agglutinative", "en_to_x"): "cometkiwi23",
    ("isolating",     "x_to_en"): "metricx",
    ("fusional",      "x_to_en"): "cometkiwi23",
    ("fusional",      "en_to_x"): "cometkiwi23",
}

N_BOOTSTRAP = 1000
RNG = np.random.default_rng(42)


def load_metric_scores(lang: str) -> pd.DataFrame | None:
    """Load all available metric CSVs for a language, merge on (segment_id, row_idx)."""
    base = None
    for metric in METRICS:
        path = RESULTS / f"scores_{metric}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        df = df[df["lang"] == lang].copy().reset_index(drop=True)
        if df.empty:
            continue
        df["_row_idx"] = df.groupby("segment_id").cumcount()
        if base is None:
            base = df[["segment_id", "_row_idx"]].copy()
            base[metric] = df[metric].values
        else:
            base[metric] = df[metric].values
    return base


def bootstrap_winner_fraction_ci(winner_flags: list[bool], n_boot: int = N_BOOTSTRAP,
                                  ci: float = 0.95) -> tuple[float, float]:
    """Bootstrap 95% CI on the fraction of True values by resampling the list."""
    if not winner_flags:
        return (float("nan"), float("nan"))
    arr = np.array(winner_flags, dtype=float)
    n = len(arr)
    boot_fracs = [RNG.choice(arr, size=n, replace=True).mean() for _ in range(n_boot)]
    alpha = (1 - ci) / 2
    return (float(np.quantile(boot_fracs, alpha)),
            float(np.quantile(boot_fracs, 1 - alpha)))


def loo_predict(winner_rows: list[dict], target_lang: str,
                morph: str, direction: str) -> str | None:
    """Return LOO prediction: majority winner among languages other than target_lang."""
    others = [r for r in winner_rows
              if r["lang"] != target_lang
              and r["morphology"] == morph
              and r["direction"] == direction]
    if not others:
        return None
    from collections import Counter
    counts = Counter(r["best_metric"] for r in others)
    return counts.most_common(1)[0][0]


def main():
    print("=" * 70)
    print("Direction-Separated Correlation Analysis (expanded, LOO, bootstrap)")
    print("=" * 70)
    print()

    print(f"Loading WMT DA data for {len(ALL_LANGS)} languages: {ALL_LANGS}")
    da_df = load_wmt_da(target_langs=ALL_LANGS)
    if da_df.empty:
        print("ERROR: No DA data loaded.", file=sys.stderr)
        sys.exit(1)
    print(f"  Loaded {len(da_df):,} DA rows for: {sorted(da_df['lang'].unique())}")
    print()

    all_corr_rows = []

    for lang in ALL_LANGS:
        lang_da = da_df[da_df["lang"] == lang].copy().reset_index(drop=True)
        if lang_da.empty:
            print(f"  {lang}: no DA data, skipping.")
            continue

        lang_da["direction"] = (
            lang_da["segment_id"]
            .str.extract(r"^([a-z]+-[a-z]+)", expand=False)
            .apply(lambda lp: (
                "x_to_en" if lp.endswith("-en")
                else ("en_to_x" if lp.startswith("en-") else "pivot")
            ))
        )
        lang_da["_row_idx"] = lang_da.groupby("segment_id").cumcount()

        metric_scores = load_metric_scores(lang)
        if metric_scores is None:
            print(f"  {lang}: no metric scores found, skipping.")
            continue

        merged = lang_da[["segment_id", "quality_score", "direction", "_row_idx"]].merge(
            metric_scores, on=["segment_id", "_row_idx"], how="inner"
        )

        directions = merged["direction"].value_counts()
        print(f"  {lang}: {len(merged):,} rows | {dict(directions)}")

        for direction, grp in merged.groupby("direction"):
            if direction == "pivot":
                continue
            human = grp["quality_score"].values
            n = len(grp)
            morph = MORPHOLOGY.get(lang, "fusional")

            for metric in METRICS:
                if metric not in grp.columns:
                    continue
                m_vals = grp[metric].values
                valid = ~(np.isnan(human) | np.isnan(m_vals))
                if valid.sum() < 20:
                    continue
                rho, _ = spearmanr(human[valid], m_vals[valid])
                all_corr_rows.append({
                    "lang": lang, "direction": direction, "morphology": morph,
                    "metric": metric, "spearman_r": rho, "n": int(valid.sum()),
                })

    if not all_corr_rows:
        print("ERROR: No correlation rows computed.", file=sys.stderr)
        sys.exit(1)

    results_df = pd.DataFrame(all_corr_rows)

    # ------------------------------------------------------------------ #
    # Build winner table                                                   #
    # ------------------------------------------------------------------ #
    winner_rows = []
    for (lang, direction), grp in results_df.groupby(["lang", "direction"]):
        grp_key = grp[grp["metric"].isin(KEY_METRICS)]
        if grp_key.empty:
            continue
        best_idx = grp_key["spearman_r"].idxmax()
        best_metric = grp_key.loc[best_idx, "metric"]
        best_rho = grp_key.loc[best_idx, "spearman_r"]
        n = grp_key["n"].max()
        morph = MORPHOLOGY.get(lang, "fusional")

        ck23_row = grp_key[grp_key["metric"] == "cometkiwi23"]
        ck23_rho = ck23_row["spearman_r"].values[0] if not ck23_row.empty else float("nan")
        comet_row = grp_key[grp_key["metric"] == "comet"]
        comet_rho = comet_row["spearman_r"].values[0] if not comet_row.empty else float("nan")
        mx_row = grp_key[grp_key["metric"] == "metricx"]
        mx_rho = mx_row["spearman_r"].values[0] if not mx_row.empty else float("nan")

        predicted = LOOKUP_TABLE.get((morph, direction), "unknown")
        correct = (best_metric == predicted
                   or ("cometkiwi" in best_metric and "cometkiwi" in predicted))

        winner_rows.append({
            "lang": lang, "direction": direction, "morphology": morph,
            "best_metric": best_metric, "best_rho": best_rho,
            "ck23_rho": ck23_rho, "comet_rho": comet_rho, "mx_rho": mx_rho,
            "n": n, "predicted": predicted, "correct": correct,
        })

    winner_df = pd.DataFrame(winner_rows)

    print()
    print("=" * 70)
    print("Per-Language, Per-Direction Results")
    print("=" * 70)
    for _, r in winner_df.sort_values(["morphology", "direction", "lang"]).iterrows():
        check = "✓" if r["correct"] else "✗"
        print(f"  {r['lang']:4s} ({r['direction']}, {r['morphology']}): "
              f"best={r['best_metric']} ρ={r['best_rho']:.3f} | "
              f"CK23={r['ck23_rho']:.3f}  COMET={r['comet_rho']:.3f}  MX={r['mx_rho']:.3f} | "
              f"predicted={r['predicted']} {check} | n={r['n']:,}")

    # ------------------------------------------------------------------ #
    # LOO cross-validation                                                 #
    # ------------------------------------------------------------------ #
    print()
    print("=" * 70)
    print("Leave-One-Out (LOO) Cross-Validation")
    print("=" * 70)

    loo_rows = []
    for _, r in winner_df.iterrows():
        lang, direction, morph = r["lang"], r["direction"], r["morphology"]
        predicted_loo = loo_predict(winner_rows, lang, morph, direction)
        if predicted_loo is None:
            continue
        actual_winner = r["best_metric"]
        loo_correct = (predicted_loo == actual_winner
                       or ("cometkiwi" in predicted_loo and "cometkiwi" in actual_winner))
        loo_rows.append({
            "lang": lang, "direction": direction, "morphology": morph,
            "actual": actual_winner, "loo_predicted": predicted_loo,
            "loo_correct": loo_correct,
        })
        check = "✓" if loo_correct else "✗"
        print(f"  {lang:4s} ({direction}, {morph}): "
              f"actual={actual_winner}  loo_pred={predicted_loo} {check}")

    loo_df = pd.DataFrame(loo_rows)
    n_loo_correct = loo_df["loo_correct"].sum()
    n_loo_total = len(loo_df)
    print(f"\n  LOO overall: {n_loo_correct}/{n_loo_total} "
          f"({100*n_loo_correct/n_loo_total:.0f}%)")

    for (morph, direction), grp in loo_df.groupby(["morphology", "direction"]):
        nc = grp["loo_correct"].sum()
        nt = len(grp)
        print(f"    {direction} × {morph}: {nc}/{nt}")

    # ------------------------------------------------------------------ #
    # Bootstrap winner-fraction CIs per cell                               #
    # ------------------------------------------------------------------ #
    print()
    print("=" * 70)
    print("Bootstrap Winner-Fraction CIs (CK23 beats COMET, per cell)")
    print("=" * 70)

    cell_ci_rows = []
    for (morph, direction), grp in winner_df.groupby(["morphology", "direction"]):
        winner_flags = (grp["ck23_rho"] > grp["comet_rho"]).tolist()
        n_langs = len(winner_flags)
        frac = sum(winner_flags) / n_langs
        ci_lo, ci_hi = bootstrap_winner_fraction_ci(winner_flags)
        predicted = LOOKUP_TABLE.get((morph, direction), "unknown")
        langs = sorted(grp["lang"].tolist())
        print(f"  {direction} × {morph}: "
              f"CK23 wins {sum(winner_flags)}/{n_langs} (frac={frac:.2f}, "
              f"95% CI [{ci_lo:.2f}, {ci_hi:.2f}]) | "
              f"predicted={predicted} | langs={langs}")
        cell_ci_rows.append({
            "morphology": morph, "direction": direction,
            "n_langs": n_langs, "n_ck23_wins": sum(winner_flags),
            "frac_ck23_wins": frac, "ci_lo": ci_lo, "ci_hi": ci_hi,
            "predicted": predicted, "langs": ",".join(langs),
        })

    cell_ci_df = pd.DataFrame(cell_ci_rows)

    # ------------------------------------------------------------------ #
    # Overall lookup table validation summary                              #
    # ------------------------------------------------------------------ #
    print()
    print("=" * 70)
    print("Lookup Table Validation Summary")
    print("=" * 70)
    n_correct = winner_df["correct"].sum()
    n_total = len(winner_df)
    print(f"  Correct: {n_correct}/{n_total} ({100*n_correct/n_total:.0f}%)")
    print(f"  LOO:     {n_loo_correct}/{n_loo_total} ({100*n_loo_correct/n_loo_total:.0f}%)")

    for (morph, direction), grp in winner_df.groupby(["morphology", "direction"]):
        nc = grp["correct"].sum()
        nt = len(grp)
        langs = sorted(grp["lang"].tolist())
        print(f"    {direction} × {morph}: {nc}/{nt}  langs={langs}")

    # ------------------------------------------------------------------ #
    # Direction × Morphology cell means                                    #
    # ------------------------------------------------------------------ #
    print()
    print("=" * 70)
    print("Direction × Morphology Mean Spearman ρ (CK23 vs COMET vs MetricX)")
    print("=" * 70)
    for direction in ["x_to_en", "en_to_x"]:
        for morph in ["agglutinative", "fusional", "isolating"]:
            cell = results_df[
                (results_df["direction"] == direction) &
                (results_df["morphology"] == morph)
            ]
            if cell.empty:
                continue
            ck23_cell = cell[cell["metric"] == "cometkiwi23"]["spearman_r"]
            comet_cell = cell[cell["metric"] == "comet"]["spearman_r"]
            mx_cell = cell[cell["metric"] == "metricx"]["spearman_r"]
            langs = sorted(cell["lang"].unique())
            print(f"  {direction} × {morph}: "
                  f"CK23={ck23_cell.mean():.3f}  COMET={comet_cell.mean():.3f}  "
                  f"MX={mx_cell.mean():.3f}  n_langs={len(langs)}  langs={langs}")

    # ------------------------------------------------------------------ #
    # Save outputs                                                         #
    # ------------------------------------------------------------------ #
    results_df.to_csv(RESULTS / "direction_separated_correlations.csv", index=False)
    winner_df.to_csv(RESULTS / "direction_separated_winners.csv", index=False)
    cell_ci_df.to_csv(RESULTS / "direction_separated_cell_cis.csv", index=False)
    loo_df.to_csv(RESULTS / "direction_separated_loo.csv", index=False)
    print()
    print("Saved:")
    print("  results/direction_separated_correlations.csv")
    print("  results/direction_separated_winners.csv")
    print("  results/direction_separated_cell_cis.csv")
    print("  results/direction_separated_loo.csv")


if __name__ == "__main__":
    main()
