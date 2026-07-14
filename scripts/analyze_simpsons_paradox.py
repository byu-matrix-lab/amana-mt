"""Systematic year-stratified vs. pooled correlation audit (Simpson's Paradox).

For MQM languages (de, ru, zh): uses the existing tier_anomaly.csv which
already has year-stratified COMET correlations.

For DA languages (cs, fi, ja, fr, tr with multiple WMT years embedded in
segment_ids): loads WMT DA quality scores from HuggingFace, merges with
metric scores, and computes per-year Spearman ρ.

Produces:
  results/simpsons_paradox_detail.csv  — per-language, per-year Spearman ρ
  results/simpsons_summary.csv         — pooled vs. year-stratified mean, Δ

Run on the login node (internet access required for DA HF load):
  python scripts/analyze_simpsons_paradox.py
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mqmbench.config import init_settings, settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_year(segment_id: str) -> str | None:
    m = re.search(r"_(\d{4})_", str(segment_id))
    return m.group(1) if m else None


def spearman_rho(x: np.ndarray, y: np.ndarray) -> float | None:
    valid = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(valid) < 30:
        return None
    return float(spearmanr(valid["x"], valid["y"]).statistic)


def main():
    init_settings(str(PROJECT_ROOT / "settings.toml"))
    results_dir = PROJECT_ROOT / Path(settings.data.results_dir)

    # ------------------------------------------------------------------ #
    # 1.  MQM languages: read existing tier_anomaly.csv                   #
    # ------------------------------------------------------------------ #
    anomaly = pd.read_csv(results_dir / "tier_anomaly.csv")
    comet_anomaly = anomaly[(anomaly["metric"] == "comet") & (anomaly["year"] != "unknown")].copy()

    summary_rows = []
    detail_rows = []

    for lang in comet_anomaly["lang"].unique():
        lang_df = comet_anomaly[comet_anomaly["lang"] == lang]
        pooled = lang_df["aggregate_spearman_r"].iloc[0]
        year_rhos = dict(zip(lang_df["year"].astype(str), lang_df["year_spearman_r"]))
        strat_mean = float(np.mean(list(year_rhos.values())))
        for yr, rho in year_rhos.items():
            n = lang_df[lang_df["year"].astype(str) == yr]["n"].values[0]
            detail_rows.append({"lang": lang, "year": yr, "n": n,
                                 "year_spearman_r": rho, "pooled_spearman_r": pooled,
                                 "source": "mqm"})
        summary_rows.append({
            "lang": lang, "n_years": len(year_rhos),
            "years": ",".join(sorted(year_rhos.keys())),
            "pooled_rho": pooled, "stratified_mean_rho": strat_mean,
            "suppression_delta": strat_mean - pooled,
            "min_year_rho": min(year_rhos.values()),
            "max_year_rho": max(year_rhos.values()),
            "source": "mqm",
        })

    # ------------------------------------------------------------------ #
    # 2.  DA languages: load quality scores and compute per-year ρ        #
    # ------------------------------------------------------------------ #
    scores_comet = pd.read_csv(results_dir / "scores_comet.csv")
    # Identify DA languages with year in segment_id
    scores_comet["year"] = scores_comet["segment_id"].apply(parse_year)
    da_multi = (
        scores_comet[scores_comet["year"].notna()]
        .groupby("lang")["year"].nunique()
    )
    da_multi_langs = da_multi[da_multi >= 2].index.tolist()
    # Exclude MQM langs already handled
    mqm_langs = comet_anomaly["lang"].unique().tolist()
    da_multi_langs = [l for l in da_multi_langs if l not in mqm_langs]

    if da_multi_langs:
        print(f"Loading WMT DA for multi-year DA languages: {da_multi_langs}")
        try:
            from datasets import load_dataset
            da_raw = load_dataset("RicardoRei/wmt-da-human-evaluation", split="train").to_pandas()
        except Exception as exc:
            print(f"  WARNING: Could not load WMT DA from HuggingFace: {exc}")
            print("  DA year-stratified analysis skipped.")
            da_raw = None

        if da_raw is not None:
            from mqmbench.data.utils import build_segment_id, lang_from_pair, rename_wmt_columns
            da_raw = rename_wmt_columns(da_raw)
            if "score" in da_raw.columns:
                da_raw = da_raw.rename(columns={"score": "quality_score"})
            da_raw["segment_id"] = build_segment_id(da_raw)
            da_raw["lang"] = da_raw["lp"].apply(lang_from_pair)

            for lang in da_multi_langs:
                lang_scores = scores_comet[scores_comet["lang"] == lang][["segment_id", "comet", "year"]]
                lang_da = da_raw[da_raw["lang"] == lang][["segment_id", "quality_score"]]
                merged = lang_scores.merge(lang_da, on="segment_id", how="inner")

                if merged.empty:
                    print(f"  WARNING: no overlap for {lang} — skipping")
                    continue

                years_present = sorted(merged["year"].dropna().unique())
                if len(years_present) < 2:
                    continue

                pooled = spearman_rho(merged["comet"].values, merged["quality_score"].values)
                if pooled is None:
                    continue

                year_rhos = {}
                for yr in years_present:
                    yr_df = merged[merged["year"] == yr]
                    rho = spearman_rho(yr_df["comet"].values, yr_df["quality_score"].values)
                    if rho is not None:
                        year_rhos[yr] = rho
                        detail_rows.append({
                            "lang": lang, "year": yr,
                            "n": len(yr_df[["comet", "quality_score"]].dropna()),
                            "year_spearman_r": rho, "pooled_spearman_r": pooled,
                            "source": "da",
                        })

                if not year_rhos:
                    continue
                strat_mean = float(np.mean(list(year_rhos.values())))
                summary_rows.append({
                    "lang": lang, "n_years": len(year_rhos),
                    "years": ",".join(sorted(year_rhos.keys())),
                    "pooled_rho": pooled, "stratified_mean_rho": strat_mean,
                    "suppression_delta": strat_mean - pooled,
                    "min_year_rho": min(year_rhos.values()),
                    "max_year_rho": max(year_rhos.values()),
                    "source": "da",
                })

    # ------------------------------------------------------------------ #
    # 3.  Output                                                           #
    # ------------------------------------------------------------------ #
    detail_df = pd.DataFrame(detail_rows)
    summary_df = pd.DataFrame(summary_rows).sort_values("suppression_delta", ascending=False)

    detail_df.to_csv(results_dir / "simpsons_paradox_detail.csv", index=False)
    summary_df.to_csv(results_dir / "simpsons_summary.csv", index=False)

    print("\n" + "=" * 64)
    print("Simpson's Paradox Audit — COMET Year-Stratified vs. Pooled")
    print("=" * 64)
    print(f"{'Lang':<6} {'Src':<4} {'Yrs':>4}  {'Pooled ρ':>9}  {'Strat mean':>11}  {'Δ':>8}")
    print("-" * 64)
    for _, row in summary_df.iterrows():
        flag = "  *** SEVERE" if row["suppression_delta"] > 0.15 else (
               "  *" if row["suppression_delta"] > 0.05 else "")
        print(f"{row['lang']:<6} {row['source']:<4} {int(row['n_years']):>4}  "
              f"{row['pooled_rho']:>9.3f}  {row['stratified_mean_rho']:>11.3f}  "
              f"{row['suppression_delta']:>8.3f}{flag}")

    severe = summary_df[summary_df["suppression_delta"] > 0.10]
    print(f"\nLanguages with suppression >0.10: {', '.join(severe['lang'].tolist()) or 'none'}")
    print(f"\nSaved: results/simpsons_summary.csv")
    print(f"Saved: results/simpsons_paradox_detail.csv")


if __name__ == "__main__":
    main()
