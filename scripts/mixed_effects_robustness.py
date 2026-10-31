"""Robustness check requested by WMT26 Reviewer 2 (Q1/Q2/Q6): the headline
eta^2_dir / eta^2_morph ANOVA treats each (language, direction) row as an
independent observation, but the 12 MIXED_LANGS contribute two rows each
(one per direction) from the same underlying language. This fits a linear
mixed-effects model with language as a random intercept to check whether
direction remains the dominant predictor once that non-independence is
modeled explicitly, rather than assumed away.

Not part of the main SSOT pipeline (generate_paper_stats.py) — this is a
one-off robustness check for the response to reviewers / camera-ready, not a
headline number. Prints results; does not write to paper_stats.json.

Run from project root:
    python scripts/mixed_effects_robustness.py
"""
import sys
from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_paper_stats import build_corrected_lang_dir_rho


def base_lang(lang: str) -> str:
    # Mixed-direction pseudo-language labels look like "et_x_t" / "et_en_" —
    # strip the direction suffix to recover the true language identity for
    # the random-effects grouping variable.
    for suffix in ("_x_t", "_en_"):
        if lang.endswith(suffix):
            return lang[: -len(suffix)]
    return lang


def main():
    df = build_corrected_lang_dir_rho("comet").dropna(subset=["spearman_r"])
    df["base_lang"] = df["lang"].apply(base_lang)

    n_langs = df["base_lang"].nunique()
    n_obs = len(df)
    n_multi = (df.groupby("base_lang").size() > 1).sum()
    print(f"n_obs={n_obs}, n_unique_languages={n_langs}, "
          f"languages contributing >1 row={n_multi}")
    print()

    model = smf.mixedlm(
        "spearman_r ~ C(direction) + C(morphology)",
        data=df,
        groups=df["base_lang"],
    )
    result = model.fit(reml=True)
    print(result.summary())
    print()

    # Variance components: how much of the residual variance is the language
    # random intercept absorbing (i.e. how non-independent the repeated
    # mixed-language observations actually are).
    group_var = result.cov_re.iloc[0, 0]
    resid_var = result.scale
    icc = group_var / (group_var + resid_var)
    print(f"Random-intercept variance (language) = {group_var:.4f}")
    print(f"Residual variance                    = {resid_var:.4f}")
    print(f"ICC (language)                        = {icc:.4f}")
    print()

    print("Fixed-effect p-values:")
    for name, p in result.pvalues.items():
        print(f"  {name}: p={p:.4g}")


if __name__ == "__main__":
    main()
