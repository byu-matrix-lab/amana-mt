#!/usr/bin/env python3
r"""
Generate results/paper_stats.json — the single JSON SSOT for every numeric
claim in the paper — from results CSVs.

This is the ONLY script that computes paper statistics. It used to be four
separate scripts (generate_macros.py, recompute_dir_morph_table.py,
generate_yearstrat_macros.py, generate_hebrew_discrimination_macros.py) that
each did their own read-merge-write against paper_stats.json, in a specific
undocumented run order, each with its own copy of "purge my old keys first"
boilerplate. That shape caused two real bugs in one night: a stale key
(SepCK23*) left behind after a rename because merge-only-adds never
removes anything, and hours lost to remembering which script owned which
macro. One script that rebuilds the whole stats dict from scratch every run
and writes it once cannot have either problem — there's no "old run" to
leave stale keys from.

Every numeric claim in the paper should trace to an entry here. Run this,
then scripts/render_macros.py to render the JSON into
latex/macros_generated.tex, then scripts/assert_paper_invariants.py before
compiling. See render_macros.py's docstring for the full pipeline.

build_corrected_lang_dir_rho() is also imported directly by
assert_paper_invariants.py, which is why all execution below is wrapped in
main() — importing this module must not have the side effect of recomputing
and overwriting paper_stats.json.

Run from the project root:
    python3 scripts/generate_paper_stats.py
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from mqmbench.analysis.correlation import (
    MORPHOLOGY_TYPES, TRANSLATION_DIRECTIONS, TIER2_LANGS,
    LANGUAGE_FAMILIES, SCRIPT_TYPES, correlate_metric_vs_human,
)
from mqmbench.analysis.metric_scope import apply_metric_scope
from mqmbench.data.wmt_mqm import (
    load_span_fallback_scores,
)
from mqmbench.data.converter import annotations_to_sentence_scores
from mqmbench.config import init_settings, settings as mqm_settings

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

from mqmbench.analysis.correlation import MIXED_DIRECTION_LANGS as MIXED_LANGS  # single source (2026-11-09)

# Table 4/6/7's per-cell language cohorts are DERIVED from the single canonical
# MORPHOLOGY_TYPES dict (correlation.py), not hand-typed per cell. A previous
# version hardcoded a separate AGGLUTIN_7 list (and separate literal fusional
# lists) that silently drifted from MORPHOLOGY_TYPES for Hausa — one file said
# fusional, another said agglutinative, and nothing caught it until a reviewer
# did. Deriving membership from one dict makes that class of bug impossible:
# there is now exactly one place to change a language's morphology type.
_LANG_TO_MORPH_CANONICAL = {lang: m for m, langs in MORPHOLOGY_TYPES.items() for lang in langs}
# Eligibility (which WMT DA languages participate in Table 4/6/7's lookup-table
# analysis) is a data/curation fact, not a morphology fact, so it's still an
# explicit list: MIXED_LANGS (both directions) plus ps (X->en only) and lv
# (en->X only). De/ru/es (Tier-1a MQM) and uk (domain-confound outlier) are
# deliberately excluded — case studies elsewhere, not clean typology cells.
_XTOEN_LOOKUP_LANGS = sorted(MIXED_LANGS | {"ps"})
_ENTOX_LOOKUP_LANGS = sorted(MIXED_LANGS | {"lv"})
AGGLUTIN_LANGS = sorted(l for l in MIXED_LANGS if _LANG_TO_MORPH_CANONICAL.get(l) == "agglutinative")
XTOEN_FUSIONAL_LANGS = sorted(l for l in _XTOEN_LOOKUP_LANGS if _LANG_TO_MORPH_CANONICAL.get(l) == "fusional")
ENTOX_FUSIONAL_LANGS = sorted(l for l in _ENTOX_LOOKUP_LANGS if _LANG_TO_MORPH_CANONICAL.get(l) == "fusional")

stats: dict[str, dict] = {}  # macro_name -> {value, fmt, source, note}


def add(key: str, value, fmt_value: str, source: str, note: str = "") -> None:
    if key in stats:
        raise ValueError(f"Duplicate key: {key}")
    stats[key] = {"value": value, "fmt": fmt_value, "source": source, "note": note}


# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def fmt_rho(v) -> str:
    """Correlation as .XXX, no leading zero."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return r"\text{---}"
    s = f"{v:.3f}"
    return s.lstrip("0") if s != "0.000" else ".000"


def fmt3(v) -> str:
    """3-decimal, leading zero kept — for gap/eta/CI values shown inline (0.387)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "---"
    return f"{v:.3f}"


def fmt2(v) -> str:
    """2-decimal, leading zero kept — for bracket-notation ranges ([0.38, 0.50])."""
    return f"{v:.2f}"


def fmt_signed3(v) -> str:
    """3-decimal with explicit +/- sign — for deltas (+0.285, -0.038)."""
    sign = "+" if v >= 0 else "-"
    return f"{sign}{abs(v):.3f}"


def fmt_n(v) -> str:
    """Integer with LaTeX thousand separator: 49{,}741"""
    return f"{int(v):,}".replace(",", "{,}")


def fmt_t(v) -> str:
    i = int(round(v))
    sign = "+" if i > 0 else ""
    return sign + f"{i:,}".replace(",", "{,}")


def fmt_pval(v) -> str:
    if v == 0.0:
        return "0"
    exp = int(math.floor(math.log10(abs(v))))
    mantissa = v / (10 ** exp)
    return rf"{mantissa:.1f}\times10^{{{exp}}}"


# ─────────────────────────────────────────────────────────────────────────────
# Pure, standalone functions — safe at module level since importing this
# module (e.g. from assert_paper_invariants.py) must not trigger recomputation.
# ─────────────────────────────────────────────────────────────────────────────

def build_corrected_lang_dir_rho(metric: str) -> pd.DataFrame:
    """Return DataFrame with (lang, direction, morphology, spearman_r) for every Tier-1 language."""
    corr = pd.read_csv(RESULTS / "correlations.csv")
    lang_to_dir = {lang: d for d, langs in TRANSLATION_DIRECTIONS.items() for lang in langs}
    lang_to_morph = {lang: m for m, langs in MORPHOLOGY_TYPES.items() for lang in langs}

    single_rows = []
    for lang, grp in corr[corr["metric"] == metric].groupby("lang"):
        if lang in MIXED_LANGS or lang in TIER2_LANGS:
            continue
        direction = lang_to_dir.get(lang, "en_to_x")
        morph = lang_to_morph.get(lang, "fusional")
        rho = grp["spearman_r"].mean()
        single_rows.append({"lang": lang, "direction": direction, "morphology": morph, "spearman_r": rho})
    single_df = pd.DataFrame(single_rows)

    sep_path = RESULTS / "direction_separated_correlations.csv"
    sep = pd.read_csv(sep_path)
    mixed_rows = []
    for (lang, direction), grp in sep[(sep["metric"] == metric) &
                                       (sep["lang"].isin(MIXED_LANGS))].groupby(["lang", "direction"]):
        morph = grp["morphology"].iloc[0]
        rho = grp["spearman_r"].mean()
        mixed_rows.append({"lang": f"{lang}_{direction[:3]}", "direction": direction,
                            "morphology": morph, "spearman_r": rho})
    mixed_df = pd.DataFrame(mixed_rows)
    return pd.concat([single_df, mixed_df], ignore_index=True)


def cell_stats(rho_vals: list) -> dict:
    if len(rho_vals) == 0:
        return {"mean": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"), "n": 0}
    mean_r = float(np.mean(rho_vals))
    if len(rho_vals) >= 3:
        rng = np.random.default_rng(42)
        boot = [float(np.mean(rng.choice(rho_vals, size=len(rho_vals), replace=True))) for _ in range(2000)]
        ci_lo, ci_hi = float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))
    else:
        ci_lo = ci_hi = float("nan")
    return {"mean": mean_r, "ci_lo": ci_lo, "ci_hi": ci_hi, "n": len(rho_vals)}


def compute_eta_sq(df: pd.DataFrame) -> dict:
    y = df["spearman_r"].dropna().values
    if len(y) < 4:
        return {"dir": float("nan"), "morph": float("nan"), "cell": float("nan"), "n_cells": 0, "n_units": len(y)}
    grand = y.mean()
    ss_total = ((y - grand) ** 2).sum()
    if ss_total == 0:
        return {"dir": 0.0, "morph": 0.0, "cell": 0.0, "n_cells": 0, "n_units": len(y)}
    dir_means = df.groupby("direction")["spearman_r"].mean()
    morph_means = df.groupby("morphology")["spearman_r"].mean()
    ss_dir = sum((df["direction"] == d).sum() * (m - grand) ** 2 for d, m in dir_means.items())
    ss_morph = sum((df["morphology"] == mt).sum() * (m - grand) ** 2 for mt, m in morph_means.items())
    # Between-cell eta^2 (one-way ANOVA over the direction x morphology cells),
    # as the paper defines eta^2_cell. Fixed 2026-11-09: this previously
    # returned 1 - eta_dir - eta_morph, a residual that also contains the
    # within-cell variance (.618 published vs .405 between-cell).
    cell_means = df.groupby(["direction", "morphology"])["spearman_r"].agg(["mean", "size"])
    ss_cell = float((cell_means["size"] * (cell_means["mean"] - grand) ** 2).sum())
    return {"dir": float(ss_dir / ss_total), "morph": float(ss_morph / ss_total),
            "cell": ss_cell / ss_total, "n_cells": int(len(cell_means)), "n_units": int(len(df))}


def main():
    # ─────────────────────────────────────────────────────────────────────
    # SECTION 1: Table 1 tier means, per-language, bootstrap CIs, Williams tests
    # (formerly generate_macros.py)
    # ─────────────────────────────────────────────────────────────────────
    tier_df = pd.read_csv(RESULTS / "tier_summary.csv")
    da_df = pd.read_csv(RESULTS / "direction_analysis.csv")
    wt_df = pd.read_csv(RESULTS / "williams_tests.csv")
    corr_df = pd.read_csv(RESULTS / "correlations.csv")

    # ─────────────────────────────────────────────────────────────────────
    # HEBREW FIX (advisor review, 2026-09-11): correlations.csv, direction_
    # analysis.csv, and tier_summary.csv are all unreliable for Hebrew right
    # now. Root cause chain: (1) compute_he_scores.py scored COMET-22,
    # BLEURT, xCOMET, and MetricX against an empty reference string instead
    # of the real WMT23 one; (2) fixing that exposed a second bug -- Hebrew's
    # segment_id collided across genuinely different segments, which is now
    # fixed in converter.py; (3) the pipeline's own --analysis-only merge
    # decides whether to do a real segment_id join or fall back to fragile
    # positional alignment based on whether segment_id is unique ACROSS THE
    # WHOLE FILE, not just within Hebrew -- since other languages (e.g.
    # Ukrainian) are legitimately non-unique by a different, harmless
    # mechanism, this forces positional alignment for every language
    # including Hebrew, whose row order no longer matches after repeated
    # checkpoint edits tonight. Net effect: ALL NINE metrics' Hebrew rows in
    # corr_df/da_df are currently wrong, including bleu/bertscore/chrf/
    # cometkiwi/cometkiwi23, which were never touched by bugs (1) or (2) and
    # have verified-correct checkpoint files.
    #
    # Rather than risk a third edit to pipeline.py's merge logic tonight,
    # recompute Hebrew directly here using the exact same correlate_metric_
    # vs_human() function the rest of the pipeline uses (so methodology stays
    # identical), against the verified-correct checkpoint files, and patch
    # corr_df/da_df in place immediately after loading -- every downstream
    # macro in this script already reads from these dataframes, so this is
    # the single point where the fix has to happen.
    # he-en and en-es are the ONLY two language pairs that go through the
    # span-fallback path (load_wmt_mqm_spans + ref_lookups), so they are the
    # only two languages this class of bug can touch -- confirmed Spanish
    # (es) has the identical symptom (spearman_r near zero for every metric,
    # including reference-free cometkiwi23) via the same root cause chain.
    _SPAN_LANG_SPECS = {
        "he": dict(lp="he-en", testset="wmt23",
                   resource_tier="high", annotation_tier="human_mqm",
                   language_family="afro_asiatic", script_type="abjad",
                   domain="unknown", direction="x_to_en"),
        # Offsets/references now come from mqmbench.data.wmt_mqm (shared).
        "es": dict(lp="en-es", testset="wmt24",
                   resource_tier="medium", annotation_tier="human_mqm",
                   language_family="indo_european", script_type="alphabetic",
                   domain="unknown", direction="en_to_x"),
    }

    def _build_span_lang_correct_rows(lang: str) -> pd.DataFrame:
        spec = _SPAN_LANG_SPECS[lang]
        init_settings(str(ROOT / "settings.toml"))
        span_dir = mqm_settings.data.wmt_mqm_span_dir
        # Shared builder (2026-11-09): same references/offsets/parsing as pipeline.py.
        lang_df = load_span_fallback_scores(span_dir, [spec["lp"]])

        rows = []
        for metric in ("bleu", "chrf", "bertscore", "bleurt", "comet", "xcomet",
                        "cometkiwi", "cometkiwi23", "metricx"):  # GEMBA excluded (metric_scope)
            ckpt_path = RESULTS / f"scores_{metric}.csv"
            if not ckpt_path.exists():
                continue
            ckpt = pd.read_csv(ckpt_path)
            ckpt_lang = apply_metric_scope(ckpt[ckpt.lang == lang], metric)
            if ckpt_lang.empty or ckpt_lang[metric].isna().all():
                continue
            merged = lang_df[["segment_id", "quality_score", "source"]].merge(
                ckpt_lang[["segment_id", metric]], on="segment_id", how="inner"
            )
            result = correlate_metric_vs_human(
                merged["quality_score"].tolist(), merged[metric].tolist(), metric, lang, n_boot=1000,
                groups=merged["source"].tolist(),
            )
            rows.append(result)

        # Ensemble has no checkpoint file of its own (pipeline.py computes it
        # on the fly from min-max-normalized neural-metric scores, GLOBALLY
        # normalized across every row in the whole dataset, not per language)
        # -- found missing entirely for he/es (0 rows) because that on-the-fly
        # computation runs on the pipeline's fragile merge, which silently
        # drops he/es. Rebuild it here from the now-corrected component
        # checkpoints, replicating the exact global-min-max scope so the
        # result is consistent with every other language's ensemble value.
        _neural = ["comet", "xcomet", "cometkiwi", "cometkiwi23", "metricx"]
        _ens_merged = lang_df[["segment_id", "quality_score", "source"]]
        for _nm in _neural:
            _nckpt = pd.read_csv(RESULTS / f"scores_{_nm}.csv")
            _col_min, _col_max = _nckpt[_nm].min(), _nckpt[_nm].max()
            _nlang = _nckpt[_nckpt.lang == lang][["segment_id", _nm]].copy()
            if _col_max > _col_min:
                _nlang[_nm] = (_nlang[_nm] - _col_min) / (_col_max - _col_min)
            _ens_merged = _ens_merged.merge(_nlang, on="segment_id", how="inner")
        _ens_merged["ensemble"] = _ens_merged[_neural].mean(axis=1)
        rows.append(correlate_metric_vs_human(
            _ens_merged["quality_score"].tolist(), _ens_merged["ensemble"].tolist(), "ensemble", lang, n_boot=1000,
            groups=_ens_merged["source"].tolist(),
        ))

        out = pd.DataFrame(rows)
        for k in ("resource_tier", "annotation_tier", "language_family", "script_type", "domain", "direction"):
            out[k] = spec[k]

        # williams_tests.csv (used by the "significant at every Tier~1
        # language" claim in \S\ref{sec:results}) is written by pipeline.py's
        # run_williams_tests() from the SAME fragile full-dataset merge that
        # drops/breaks he/es -- so its he/es rows are stale relative to the
        # corrected checkpoints above. Recompute directly here on a wide
        # (segment_id x all-metrics) frame built from the corrected data, so
        # the Williams comparisons are consistent with every other number in
        # this script.
        from mqmbench.analysis.correlation import run_williams_tests
        _wide = lang_df[["segment_id", "quality_score"]].copy()
        for metric in ("bleu", "chrf", "bertscore", "bleurt", "comet", "xcomet",
                        "cometkiwi", "cometkiwi23", "metricx"):  # GEMBA excluded (metric_scope)
            ckpt_path = RESULTS / f"scores_{metric}.csv"
            if not ckpt_path.exists():
                continue
            ckpt = pd.read_csv(ckpt_path)
            ckpt_lang = apply_metric_scope(ckpt[ckpt.lang == lang], metric)[["segment_id", metric]]
            if ckpt_lang.empty or ckpt_lang[metric].isna().all():
                continue
            _wide = _wide.merge(ckpt_lang, on="segment_id", how="left")
        _wide = _wide.merge(_ens_merged[["segment_id", "ensemble"]], on="segment_id", how="left")
        _wide["lang"] = lang
        _metric_cols = [c for c in _wide.columns if c not in ("segment_id", "quality_score", "lang")]
        out.attrs["williams"] = run_williams_tests(_wide, _metric_cols)
        return out

    _corrected = {lang: _build_span_lang_correct_rows(lang) for lang in _SPAN_LANG_SPECS}
    for lang, _fixed in _corrected.items():
        print(f"\n{lang} recomputed directly ({len(_fixed)} metrics, verified-correct references):")
        print(_fixed[["metric", "n", "spearman_r", "pairwise_acc", "spa"]].to_string(index=False))

    # Write the corrected he/es rows back into correlations.csv on disk too --
    # not just the in-memory corr_df/da_df above. build_corrected_lang_dir_rho()
    # (used for the direction x morphology 2x3 analysis, the mixed-effects
    # model, DiD, and the decision-procedure table -- the paper's central
    # novel contribution) re-reads correlations.csv fresh from disk rather than
    # taking the in-memory corr_df, so without this the deepest analyses in the
    # paper would silently keep using the pre-fix, broken he/es numbers even
    # though every other table looked correct.
    _corr_csv_path = RESULTS / "correlations.csv"
    _corr_on_disk = pd.read_csv(_corr_csv_path)
    _corr_on_disk = _corr_on_disk[~_corr_on_disk.lang.isin(_SPAN_LANG_SPECS.keys())]
    for lang, _fixed in _corrected.items():
        _cols = [c for c in _fixed.columns if c in _corr_on_disk.columns]
        _new_rows = _fixed[_cols].copy()
        _new_rows["lang"] = lang
        _corr_on_disk = pd.concat([_corr_on_disk, _new_rows], ignore_index=True)
    _corr_on_disk = _corr_on_disk[pd.read_csv(_corr_csv_path, nrows=0).columns.tolist()]
    _corr_on_disk.to_csv(_corr_csv_path, index=False)
    print(f"Wrote corrected he/es rows into {_corr_csv_path}")

    _wt_csv_path = RESULTS / "williams_tests.csv"
    _wt_on_disk = pd.read_csv(_wt_csv_path)
    _wt_on_disk = _wt_on_disk[~_wt_on_disk.lang.isin(_SPAN_LANG_SPECS.keys())]
    _wt_new = pd.concat([f.attrs["williams"] for f in _corrected.values()], ignore_index=True)
    _wt_on_disk = pd.concat([_wt_on_disk, _wt_new[_wt_on_disk.columns.tolist()]], ignore_index=True)
    _wt_on_disk.to_csv(_wt_csv_path, index=False)
    print(f"Wrote corrected he/es Williams tests into {_wt_csv_path}")
    wt_df = _wt_on_disk  # refresh in-memory copy read at the top of this function, before the fix ran

    for _df_name in ("corr_df", "da_df"):
        _df = corr_df if _df_name == "corr_df" else da_df
        _df = _df[~_df.lang.isin(_SPAN_LANG_SPECS.keys())]
        for lang, _fixed in _corrected.items():
            _cols = [c for c in _fixed.columns if c in _df.columns]
            _new_rows = _fixed[_cols].copy()
            _new_rows["lang"] = lang
            _df = pd.concat([_df, _new_rows], ignore_index=True)
        if _df_name == "corr_df":
            corr_df = _df
        else:
            da_df = _df

    # da_df above was only patched IN MEMORY -- results/direction_analysis.csv
    # on disk was never written back, so any script reading that file directly
    # (found: build_metric_reliability_predictor.py, the Ridge typological
    # predictor behind \S\ref{sec:predictor} and its presentation_ridge_
    # coefficients.pdf figure) was silently training on the pre-fix garbage
    # he/es rows (near-zero for every metric) -- discovered 2026-09-12 when
    # results/predictor/summary.json turned out to be dated Aug 8, predating
    # even the original Hebrew fix. Mirror the correlations.csv write-back
    # above so direction_analysis.csv can't be a second stale copy of the
    # same bug.
    _da_csv_path = RESULTS / "direction_analysis.csv"
    _da_on_disk = pd.read_csv(_da_csv_path)
    _da_on_disk = _da_on_disk[~_da_on_disk.lang.isin(_SPAN_LANG_SPECS.keys())]
    for lang, _fixed in _corrected.items():
        _cols = [c for c in _fixed.columns if c in _da_on_disk.columns]
        _new_rows = _fixed[_cols].copy()
        _new_rows["lang"] = lang
        _da_on_disk = pd.concat([_da_on_disk, _new_rows], ignore_index=True)
    _da_on_disk = _da_on_disk[pd.read_csv(_da_csv_path, nrows=0).columns.tolist()]
    _da_on_disk.to_csv(_da_csv_path, index=False)
    print(f"Wrote corrected he/es rows into {_da_csv_path}")

    # tier_summary.csv's "high"/"medium" rows are summarize_by_tier()'s simple
    # mean of per-language spearman_r/spa across each tier's languages --
    # replicate that exact averaging with the corrected he/es values
    # substituted in, rather than trusting tier_summary.csv's already-wrong
    # rows (built from the same corrupted corr_df before this fix).
    _affected_tiers = {spec["resource_tier"] for spec in _SPAN_LANG_SPECS.values()}
    _tier_fixed_parts = []
    for _tier in _affected_tiers:
        _tier_langs_corr = corr_df[(corr_df.resource_tier == _tier) & (corr_df.annotation_tier == "human_mqm")]
        _tier_fixed_parts.append(
            _tier_langs_corr.groupby(["metric", "resource_tier", "annotation_tier"])[
                [c for c in ("pairwise_acc", "spa", "pearson_r", "spearman_r", "kendall_tau") if c in _tier_langs_corr.columns]
            ].mean().reset_index()
        )
    _tier_fixed = pd.concat(_tier_fixed_parts, ignore_index=True)
    tier_df = pd.concat(
        [tier_df[~((tier_df.resource_tier.isin(_affected_tiers)) & (tier_df.annotation_tier == "human_mqm"))], _tier_fixed],
        ignore_index=True,
    )

    # Persist the corrected tier_df back to tier_summary.csv on disk -- same
    # disk/memory staleness trap as correlations.csv (build_corrected_lang_dir_rho
    # bug above): assert_paper_invariants.py and any future script that reads
    # tier_summary.csv directly must see the corrected he/es-driven averages,
    # not the pre-fix values.
    tier_df.to_csv(RESULTS / "tier_summary.csv", index=False)
    print(f"Wrote corrected he/es-driven tier averages into {RESULTS / 'tier_summary.csv'}")

    n_langs_actual = int(corr_df.lang.nunique())
    # 2026-11-10: computed, not typed. The typed 730,748 counted the pre-fix
    # he/es span block (23,730 rows; the corrected block has 18,548).
    _total_segments = int(corr_df[corr_df.metric == "comet"].n.sum())
    _n_scored = sum(1 for _ in open(RESULTS / "scores_comet.csv")) - 1
    if _total_segments != _n_scored:
        raise SystemExit(f"TotalSegments: correlations.csv sums to {_total_segments}, "
                         f"scores_comet.csv has {_n_scored} rows")
    add("TotalSegments", _total_segments, fmt_n(_total_segments), "correlations.csv",
        "Total scored segments across all tiers (sum of COMET n in correlations.csv; equals scores_comet.csv rows)")

    _tier1_total_segments = int(
        corr_df[(~corr_df.lang.isin(TIER2_LANGS)) & (corr_df.metric == "comet")].n.sum()
    )
    add("TierOneTotalSegments", _tier1_total_segments, fmt_n(_tier1_total_segments), "correlations.csv",
        "Sum of n across Tier-1a+1b languages (comet rows) — replaces a stale '371k+' claim that "
        "didn't match Tier-1a (174,077), Tier-1b (549,587), or their sum (723,664) under any "
        "aggregation tried")
    add("NumLanguages", n_langs_actual, str(n_langs_actual), "correlations.csv",
        "Unique languages with valid entries in correlations.csv (includes Tier-2 synthetic)")
    _num_metrics = int(corr_df[corr_df.metric != "ensemble"].metric.nunique())
    add("NumMetrics", _num_metrics, str(_num_metrics), "correlations.csv",
        "Distinct metrics in correlations.csv, excluding the ensemble (GEMBA removed 2026-11-10)")

    n_human_annotated = int(corr_df[~corr_df.lang.isin(TIER2_LANGS)].lang.nunique())
    add("NumHumanAnnotatedLanguages", n_human_annotated, str(n_human_annotated), "correlations.csv",
        "Languages with human (Tier-1a/1b) annotation, excluding the 7 Tier-2 synthetic languages")
    add("NumTierTwoLanguages", len(TIER2_LANGS), str(len(TIER2_LANGS)), "manual",
        "Count of TIER2_LANGS (sw, ht, lo, th, my, am, ka)")
    add("NumLanguageFamilies", len(LANGUAGE_FAMILIES), str(len(LANGUAGE_FAMILIES)),
        "src/mqmbench/analysis/correlation.py:LANGUAGE_FAMILIES",
        "Count of distinct language family keys (replaces an untraceable 'Eleven Families' "
        "presentation-slide claim; actual count is 12)")
    add("NumScriptTypes", len(SCRIPT_TYPES), str(len(SCRIPT_TYPES)),
        "src/mqmbench/analysis/correlation.py:SCRIPT_TYPES",
        "Count of distinct script type keys (logographic, alphabetic, abjad, abugida)")
    add("NumMixedLangs", len(MIXED_LANGS), str(len(MIXED_LANGS)), "manual",
        "Count of MIXED_LANGS (bidirectional languages) — replaces a stale 'Thirteen languages' "
        "claim; verified against direction_separated_correlations.csv that exactly these 12 "
        "languages have both en_to_x and x_to_en rows, no more, no fewer")
    # NOTE: NOT csv.lang.nunique() on direction_separated_correlations.csv — that
    # set is {12 MIXED_LANGS, lv, ps, km}, but Table~\ref{tab:dir_sep} doesn't
    # display km (isolating type isn't covered by that table) and DOES display
    # de-en (a held-out pair appended manually, absent from this csv). The two
    # swaps happen to net to the same count (15) but naming the wrong set would
    # be exactly the "plausible but untraceable" bug this SSOT exists to prevent.
    # Compute directly from what the table actually shows instead.
    _num_sep_langs = len(MIXED_LANGS) + 3  # + ps, lv (single-direction), + de-en (held out)
    add("NumSepLangs", _num_sep_langs, str(_num_sep_langs), "manual/tab:dir_sep",
        "Distinct languages shown in Table~\\ref{tab:dir_sep}: 12 MIXED_LANGS (each shown twice, "
        "once per direction) + ps (X->en only) + lv (en->X only) + de-en (held-out pair, starred) "
        "= 15. Deliberately excludes km, which is in direction_separated_correlations.csv but not "
        "shown in this table (isolating type not covered here).")

    METRIC_KEY = {
        "bleu": "BLEU", "chrf": "ChrF", "bertscore": "BERTScore",
        "bleurt": "BLEURT", "comet": "COMET", "xcomet": "xCOMET",
        "metricx": "MetricX", "cometkiwi": "KiwiXXII", "cometkiwi23": "KiwiXXIII",
        "gemba": "GEMBA", "ensemble": "Ensemble",
    }
    TIER_KEY = {"high": "High", "medium": "Med", "low": "Low"}

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
            add(f"Tier{mk}{tk}SPA", float(spa), fmt_rho(spa), "tier_summary.csv",
                f"{row.metric} mean SPA, {row.resource_tier} tier (averaged across annotation tiers)")

    for lang in sorted(da_df.lang.unique()):
        for metric in ("comet", "metricx", "cometkiwi23", "cometkiwi", "bertscore", "xcomet"):
            rows = da_df[(da_df.lang == lang) & (da_df.metric == metric)]
            if rows.empty:
                continue
            row = rows.iloc[0]
            if pd.isna(row.spearman_r):
                continue
            mk = {"comet": "COMET", "metricx": "MetricX", "cometkiwi23": "KiwiXXIII",
                  "cometkiwi": "Kiwi", "bertscore": "BERTScore", "xcomet": "XCOMET"}[metric]
            add(f"Lang{mk}{lang.upper()}", float(row.spearman_r), fmt_rho(row.spearman_r),
                "direction_analysis.csv",
                f"{lang} {metric} rho (direction={row.direction}, tier={row.resource_tier})")
            if metric in ("comet", "metricx"):
                # Tbl variant (fmt3, keeps leading zero): Table 7 (tab:direction_full)
                # mixes these single-direction languages' cells with the
                # \SepCOMET*/\SepMX* cells for the 12 both-direction languages,
                # which use fmt3 -- fmt_rho here would render e.g. lv as ".746"
                # next to lt's "0.790" in the same column (found 2026-09-12,
                # same bug class as the earlier de-en leading-zero fix in Table 8).
                add(f"Lang{mk}{lang.upper()}Tbl", float(row.spearman_r), fmt3(row.spearman_r),
                    "direction_analysis.csv", f"{lang} {metric} rho (Table 7 cell)")

    for lang in sorted(da_df.lang.unique()):
        rows = da_df[(da_df.lang == lang) & (da_df.metric == "comet")]
        if rows.empty:
            continue
        row = rows.iloc[0]
        if pd.isna(row.n):
            continue
        add(f"LangN{lang.upper()}", int(row.n), fmt_n(row.n), "direction_analysis.csv",
            f"Segment count for {lang}")

    for lang in ("de", "ps"):
        row = corr_df[(corr_df.lang == lang) & (corr_df.metric == "comet")].iloc[0]
        add(f"LangCOMET{lang.upper()}CIlo", float(row.spearman_ci_lo),
            fmt_rho(row.spearman_ci_lo), "correlations.csv", f"{lang} COMET 95% bootstrap CI lower bound")
        add(f"LangCOMET{lang.upper()}CIhi", float(row.spearman_ci_hi),
            fmt_rho(row.spearman_ci_hi), "correlations.csv", f"{lang} COMET 95% bootstrap CI upper bound")

    uk_row = corr_df[(corr_df.lang == "uk") & (corr_df.metric == "comet")].iloc[0]
    add("LangUKCOMETPval", float(uk_row.spearman_p), f"{uk_row.spearman_p:.2f}",
        "correlations.csv", "Ukrainian COMET Spearman p-value (domain outlier)")
    add("LangUKCOMETPairwiseAcc", float(uk_row.pairwise_acc), fmt3(uk_row.pairwise_acc),
        "correlations.csv", "Ukrainian COMET pairwise accuracy (near-chance, domain outlier)")

    wt_valid = wt_df[wt_df.metric != "ensemble"].dropna(subset=["t_statistic"])
    max_row = wt_valid.loc[wt_valid.t_statistic.idxmax()]
    min_row = wt_valid.loc[wt_valid.t_statistic.idxmin()]
    wt_all_valid = wt_df.dropna(subset=["t_statistic"])
    wt_n_min_row = wt_all_valid.loc[wt_all_valid.n.idxmin()]
    wt_n_max_row = wt_all_valid.loc[wt_all_valid.n.idxmax()]
    add("WilliamsNMin", int(wt_n_min_row.n), fmt_n(wt_n_min_row.n), "williams_tests.csv",
        f"Smallest n across Williams-tested languages (lang={wt_n_min_row.lang})")
    add("WilliamsNMax", int(wt_n_max_row.n), fmt_n(wt_n_max_row.n), "williams_tests.csv",
        f"Largest n across Williams-tested languages (lang={wt_n_max_row.lang})")
    add("WilliamsMaxT", float(max_row.t_statistic), fmt_t(max_row.t_statistic), "williams_tests.csv",
        f"Max Williams t: lang={max_row.lang} metric={max_row.metric} vs {max_row.reference_metric} n={max_row.n}")
    add("WilliamsMinT", float(min_row.t_statistic), fmt_t(min_row.t_statistic), "williams_tests.csv",
        f"Min Williams t: lang={min_row.lang} metric={min_row.metric} vs {min_row.reference_metric} n={min_row.n}")
    zu_row = wt_df[(wt_df.lang == "zu") & (wt_df.metric == "xcomet") & (wt_df.reference_metric == "comet")].iloc[0]
    add("ZuluXcometPval", float(zu_row.p_value), fmt_pval(zu_row.p_value),
        "williams_tests.csv", "Zulu xCOMET vs COMET Williams p-value")

    # Does COMET (the Williams-test reference metric) significantly beat BOTH
    # surface baselines (BLEU, chrF) at every Tier~1 (human_mqm/human_da)
    # language? Advisor review flagged the paper's blanket claim as
    # unsupported/false for Ukrainian; this computes the actual exception set
    # so the claim in \S\ref{sec:results} is exact rather than asserted.
    _tier1_langs = sorted(set(
        corr_df[corr_df.annotation_tier.isin(["human_mqm", "human_da"])].lang.unique()
    ))
    _wt_surface = wt_df[
        wt_df.lang.isin(_tier1_langs) & wt_df.metric.isin(["bleu", "chrf"])
        & (wt_df.reference_metric == "comet")
    ].dropna(subset=["p_value"])
    _wt_surface_fail = _wt_surface[~_wt_surface.significant_p05]
    _wt_fail_langs = sorted(_wt_surface_fail.lang.unique())
    add("WilliamsTierOneExceptionCount", len(_wt_fail_langs), str(len(_wt_fail_langs)),
        "williams_tests.csv",
        "Count of Tier-1 languages where COMET is NOT significantly better than "
        "both BLEU and chrF (Williams test vs. comet reference, p<0.05)")
    add("WilliamsTierOneExceptionLangs", ",".join(_wt_fail_langs), ", ".join(_wt_fail_langs),
        "williams_tests.csv", "Which Tier-1 languages fail the above (uppercase ISO codes in prose)")
    for _l in _wt_fail_langs:
        for _m in ("bleu", "chrf"):
            _r = _wt_surface[(_wt_surface.lang == _l) & (_wt_surface.metric == _m)]
            if _r.empty:
                continue
            _p = float(_r.iloc[0].p_value)
            add(f"Williams{_l.upper()}{_m.upper()}vsCOMETPval", _p, fmt_pval(_p),
                "williams_tests.csv", f"{_l} {_m} vs COMET Williams p-value (Tier-1 exception)")

    # Hypothetical: what would the High-tier COMET mean be if Spanish (WMT24
    # en-es, currently classified Medium) were grouped with High instead?
    # Used to show the medium>high gap survives (just narrows) under the
    # alternative classification, addressing a "why is Spanish Medium and
    # not High" reviewer question.
    _high_plus_es_langs = ["de", "ru", "zh", "he", "es"]
    _high_plus_es_rho = float(
        corr_df[(corr_df.lang.isin(_high_plus_es_langs)) & (corr_df.metric == "comet")]
        .groupby("lang")["spearman_r"].mean().mean()
    )
    add("TierCOMETHighPlusEsRho", _high_plus_es_rho, fmt_rho(_high_plus_es_rho), "correlations.csv",
        "Hypothetical High-tier COMET mean if Spanish were included (de,ru,zh,he,es)")

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 2: Direction x Morphology (Table 2), Direction x Metric (Table 3),
    # Table 4 lookup, Table 6/7 direction-separated appendix
    # (formerly recompute_dir_morph_table.py)
    # ─────────────────────────────────────────────────────────────────────
    metric = "comet"
    df = build_corrected_lang_dir_rho(metric)
    table_df = df[df["direction"].isin(["x_to_en", "en_to_x", "pivot"])].copy()

    print("Per-language rho used in corrected Table 2:")
    print(table_df[["lang", "direction", "morphology", "spearman_r"]]
          .sort_values(["direction", "morphology", "lang"]).to_string(index=False))
    print()

    cell_data = {}
    for direction in ["x_to_en", "en_to_x", "pivot"]:
        for morph in ["isolating", "agglutinative", "fusional"]:
            cell = table_df[(table_df["direction"] == direction) & (table_df["morphology"] == morph)]
            rho_vals = cell["spearman_r"].dropna().tolist()
            cell_data[(direction, morph)] = cell_stats(rho_vals)
            if cell_data[(direction, morph)]["n"] > 0:
                print(f"  {direction} x {morph}: n={cell_data[(direction, morph)]['n']} langs={cell['lang'].tolist()}")

    eta = compute_eta_sq(table_df[table_df["direction"].isin(["x_to_en", "en_to_x"])])
    print(f"\n  eta_dir={eta['dir']:.3f}  eta_morph={eta['morph']:.3f}  eta_cell={eta['cell']:.3f} ({eta['n_cells']} cells, {eta['n_units']} units)\n")

    _dm_names = {
        ("x_to_en", "isolating"): "DirMorphCOMETXtoEnIsolating",
        ("x_to_en", "agglutinative"): "DirMorphCOMETXtoEnAgglutin",
        ("x_to_en", "fusional"): "DirMorphCOMETXtoEnFusional",
        ("en_to_x", "agglutinative"): "DirMorphCOMETEntoXAgglutin",
        ("en_to_x", "fusional"): "DirMorphCOMETEntoXFusional",
        ("pivot", "fusional"): "DirMorphCOMETPivotFusional",
    }
    for cell_key, macro_name in _dm_names.items():
        v = cell_data[cell_key]
        add(macro_name, v["mean"], fmt3(v["mean"]), "recompute:direction_morphology",
            f"COMET mean rho: {cell_key[0]} x {cell_key[1]}, n={v['n']}")
        if v["n"] >= 3:
            add(f"{macro_name}CIlo", v["ci_lo"], fmt3(v["ci_lo"]), "recompute:direction_morphology", "bootstrap CI lower")
            add(f"{macro_name}CIhi", v["ci_hi"], fmt3(v["ci_hi"]), "recompute:direction_morphology", "bootstrap CI upper")

    add("EtaSqDir", eta["dir"], fmt3(eta["dir"]), "recompute:direction_morphology", "eta^2 direction main effect")
    add("EtaSqMorph", eta["morph"], fmt3(eta["morph"]), "recompute:direction_morphology", "eta^2 morphology main effect")
    add("EtaSqCell", eta["cell"], fmt3(eta["cell"]), "recompute:direction_morphology",
        "eta^2 between direction x morphology cells (one-way ANOVA over cells)")
    add("EtaSqNCells", eta["n_cells"], str(eta["n_cells"]), "recompute:direction_morphology",
        "number of non-empty direction x morphology cells in the eta^2 analysis")
    add("EtaSqNUnits", eta["n_units"], str(eta["n_units"]), "recompute:direction_morphology",
        "number of language(-direction) units in the eta^2 analysis")

    # Direction x metric means (Table 3)
    metric_map = {"bleu": "BLEU", "chrf": "ChrF", "comet": "COMET", "xcomet": "xCOMET", "metricx": "MetricX"}
    for metric_name, label in metric_map.items():
        df_m = build_corrected_lang_dir_rho(metric_name)
        df_m = df_m[df_m["direction"].isin(["x_to_en", "en_to_x", "pivot"])]
        for direction, dir_label in [("en_to_x", "EntoX"), ("x_to_en", "XtoEn"), ("pivot", "Pivot")]:
            vals = df_m[df_m["direction"] == direction]["spearman_r"].dropna()
            if len(vals):
                add(f"DirMetric{label}{dir_label}", float(vals.mean()), fmt3(vals.mean()),
                    "recompute:direction_metric", f"Mean rho: {metric_name} x {direction}, n={len(vals)}")

    # CKXXIII-vs-COMET means (Table 3 caption: "0.387 vs. 0.377")
    for metric_name, label in [("cometkiwi23", "CKXXIII")]:
        df_m = build_corrected_lang_dir_rho(metric_name)
        df_m = df_m[df_m["direction"].isin(["x_to_en", "en_to_x", "pivot"])]
        for direction, dir_label in [("en_to_x", "EntoX"), ("x_to_en", "XtoEn"), ("pivot", "Pivot")]:
            vals = df_m[df_m["direction"] == direction]["spearman_r"].dropna()
            if len(vals):
                add(f"DirMetric{label}{dir_label}", float(vals.mean()), fmt3(vals.mean()),
                    "recompute:direction_metric", f"Mean rho: {metric_name} x {direction}, n={len(vals)}")

    # Gap / DiD macros. No per-statistic exclusions except where the paper's own
    # prose explicitly discloses one (uk, for the fusional X->en COMET-BLEU gap).
    def cell_mean(metric_name, direction, morph, exclude=frozenset()):
        d = build_corrected_lang_dir_rho(metric_name)
        d = d[(d["direction"] == direction) & (d["morphology"] == morph) & (~d["lang"].isin(exclude))]
        return d["spearman_r"].mean() if len(d) else float("nan")

    gap_agglutin_dir = cell_mean("comet", "en_to_x", "agglutinative") - cell_mean("comet", "x_to_en", "agglutinative")
    gap_fusional_dir = cell_mean("comet", "en_to_x", "fusional") - cell_mean("comet", "x_to_en", "fusional")
    did_value = gap_fusional_dir - gap_agglutin_dir
    add("GapDirAgglutin", gap_agglutin_dir, fmt3(gap_agglutin_dir), "recompute:gaps", "en_to_x - x_to_en, agglutinative")
    add("GapDirFusional", gap_fusional_dir, fmt3(gap_fusional_dir), "recompute:gaps", "en_to_x - x_to_en, fusional")
    add("DiDValue", did_value, fmt3(did_value), "recompute:gaps", "fusional dir gap - agglutinative dir gap")

    gap_fusional_xtoen_cometbleu = (
        cell_mean("comet", "x_to_en", "fusional", {"uk"}) - cell_mean("bleu", "x_to_en", "fusional", {"uk"})
    )
    gap_agglutin_entox_cometbleu = cell_mean("comet", "en_to_x", "agglutinative") - cell_mean("bleu", "en_to_x", "agglutinative")
    add("GapCometBleuFusionalXtoEn", gap_fusional_xtoen_cometbleu, fmt3(gap_fusional_xtoen_cometbleu),
        "recompute:gaps", "COMET-BLEU gap, fusional X->en, uk excluded (disclosed in prose)")
    add("GapCometBleuAgglutinEntoX", gap_agglutin_entox_cometbleu, fmt3(gap_agglutin_entox_cometbleu),
        "recompute:gaps", "COMET-BLEU gap, agglutinative en->X")

    # Direction-controlled version of the same comparison (Sec 5.1): the
    # cross-direction pairing above (fusional X->en vs agglutinative en->X)
    # confounds morphology with direction, which the rest of the paper is
    # careful to avoid. Holding direction fixed at X->en, agglutinative
    # (0.129) is still bigger than fusional (0.061) — the claim survives
    # under the controlled comparison, so use this pairing instead.
    gap_agglutin_xtoen_cometbleu = cell_mean("comet", "x_to_en", "agglutinative") - cell_mean("bleu", "x_to_en", "agglutinative")
    add("GapCometBleuAgglutinXtoEn", gap_agglutin_xtoen_cometbleu, fmt3(gap_agglutin_xtoen_cometbleu),
        "recompute:gaps", "COMET-BLEU gap, agglutinative X->en (direction-matched contrast to fusional X->en)")

    # Table 4 lookup: narrower 15-WMT-DA-language cohort, not the broad Tier-1 ANOVA cohort.
    # De/ru/es (Tier-1a MQM) are deliberately excluded — already individual case
    # studies elsewhere (de in the neural-gap section, ru in the Simpson's-Paradox
    # section) — this reproduces the paper's pre-established n's (7,2,7,7,6,5).
    sep_df = pd.read_csv(RESULTS / "direction_separated_correlations.csv")

    def sep_rho(lang, direction, metric_name):
        row = sep_df[(sep_df.lang == lang) & (sep_df.direction == direction) & (sep_df.metric == metric_name)]
        return float(row.spearman_r.iloc[0]) if len(row) else None

    def single_rho(lang, metric_name):
        row = corr_df[(corr_df.lang == lang) & (corr_df.metric == metric_name)]
        return float(row.spearman_r.mean()) if len(row) else None

    TABLE4_CELLS = {
        "TableFourXtoEnAgglutin": ([(l, "x_to_en", "sep") for l in AGGLUTIN_LANGS], "cometkiwi23"),
        "TableFourXtoEnIsolating": ([("km", "x_to_en", "sep"), ("zh", None, "single")], "metricx"),
        # he was missing here for the same reason as the win-count above
        # (XTOEN_FUSIONAL_LANGS excludes non-mixed languages); added the same
        # way. de-en is not added here (unlike the win-count) because it has
        # no BLEU score in scores_de_en.csv, so it cannot enter a
        # Delta-rho-vs-BLEU average at all.
        "TableFourXtoEnFusional": ([(l, "x_to_en", "sep") for l in XTOEN_FUSIONAL_LANGS]
                                   + [("he", None, "single")], "cometkiwi23"),
        "TableFourEntoXAgglutin": ([(l, "en_to_x", "sep") for l in AGGLUTIN_LANGS], "metricx"),
        "TableFourEntoXFusional": ([(l, "en_to_x", "sep") for l in ENTOX_FUSIONAL_LANGS], "cometkiwi23"),
        "TableFourPivotFusional": ([(l, None, "single") for l in ["bn", "fr", "hi", "xh", "zu"]], "metricx"),
    }
    for macro_name, (members, rec_metric) in TABLE4_CELLS.items():
        gaps = []
        for lang, direction, kind in members:
            m, b = (sep_rho(lang, direction, rec_metric), sep_rho(lang, direction, "bleu")) if kind == "sep" \
                else (single_rho(lang, rec_metric), single_rho(lang, "bleu"))
            if m is not None and b is not None:
                gaps.append(m - b)
        v = sum(gaps) / len(gaps) if gaps else float("nan")
        add(macro_name, v, fmt3(v), "recompute:table4", f"n={len(gaps)}")

    # Isolating X->en per-language gaps (zh, km individually; text cites both)
    _mx_all = build_corrected_lang_dir_rho("metricx")
    _bl_all = build_corrected_lang_dir_rho("bleu")
    for lang in ["zh", "km"]:
        mx_v = _mx_all[_mx_all["lang"] == lang]["spearman_r"]
        bl_v = _bl_all[_bl_all["lang"] == lang]["spearman_r"]
        if len(mx_v) and len(bl_v):
            gap = float(mx_v.iloc[0]) - float(bl_v.iloc[0])
            add(f"Gap{lang.upper()}MetricXBleu", gap, fmt3(gap), "recompute:table4", f"{lang} MetricX-BLEU gap")

    # Hebrew CKXXIII-vs-COMET gap (the paper's headline "+0.35" claim)
    he_ck23 = single_rho("he", "cometkiwi23")
    he_comet = single_rho("he", "comet")
    if he_ck23 is not None and he_comet is not None:
        add("GapHeKiwiComet", he_ck23 - he_comet, fmt3(he_ck23 - he_comet), "recompute:hebrew", "CKXXIII - COMET, Hebrew")

    # Spanish CKXXIII-vs-COMET gap: the other largest deviation from the
    # equal-performance diagonal in fig:kiwi_scatter (found while fixing that
    # figure's caption, which had wrongly claimed no substantial outliers
    # after the Hebrew fix -- Hebrew and Spanish are, in fact, the two
    # largest deviations in the dataset, just in COMET's favor now).
    _es_ck23 = single_rho("es", "cometkiwi23")
    _es_comet = single_rho("es", "comet")
    if _es_ck23 is not None and _es_comet is not None:
        add("GapEsKiwiComet", _es_ck23 - _es_comet, fmt3(_es_ck23 - _es_comet), "recompute:hebrew", "CKXXIII - COMET, Spanish")

    # Reference point for the GEMBA-remapping-rejection note in Limitations:
    # segment-level Spearman agreement between two independently-correct
    # metrics (COMET, xCOMET) for he/es, to contrast against the near-zero
    # correlation the rejected GEMBA positional remapping produced.
    _comet_ck = pd.read_csv(RESULTS / "scores_comet.csv")
    _xcomet_ck = pd.read_csv(RESULTS / "scores_xcomet.csv")
    _cx_corrs = []
    for _l in ("he", "es"):
        _m = _comet_ck[_comet_ck.lang == _l][["segment_id", "comet"]].merge(
            _xcomet_ck[_xcomet_ck.lang == _l][["segment_id", "xcomet"]], on="segment_id")
        _cx_corrs.append(spearmanr(_m.comet, _m.xcomet).statistic)
    _cx_min = float(min(_cx_corrs))
    add("CometXcometHeEsMinRho", _cx_min, fmt2(_cx_min), "recompute:gemba_remap_check",
        "Min segment-level COMET-xCOMET Spearman r across he/es, reference point for rejecting the GEMBA remap")

    # Pashto Kiwi-22 vs COMET delta (near-parity claim)
    ps_kiwi22 = single_rho("ps", "cometkiwi")
    ps_comet = single_rho("ps", "comet")
    if ps_kiwi22 is not None and ps_comet is not None:
        d = ps_kiwi22 - ps_comet
        add("PsKiwiCometDelta", d, fmt_signed3(d), "recompute:pashto", "Kiwi-22 - COMET, Pashto")

    # Ukrainian gap to next-lowest X->en language (ja-en, direction-separated)
    uk_comet = single_rho("uk", "comet")
    ja_comet_xe = sep_rho("ja", "x_to_en", "comet")
    if uk_comet is not None and ja_comet_xe is not None:
        add("UkJaGap", ja_comet_xe - uk_comet, fmt3(ja_comet_xe - uk_comet), "recompute:ukrainian", "ja-en COMET - uk COMET")
        add("JaXtoEnRho", ja_comet_xe, fmt_rho(ja_comet_xe), "recompute:ukrainian", "ja-en direction-separated COMET rho")

    # Pivot fusional win-count (Table 4 row + Sec 4.5 text)
    PIVOT_LANGS = ["bn", "fr", "hi", "xh", "zu"]
    PIVOT_METRICS = ["bleu", "chrf", "comet", "xcomet", "metricx", "cometkiwi", "cometkiwi23"]
    metricx_wins = 0
    _pivot_winners = {}
    for lang in PIVOT_LANGS:
        sub = da_df[(da_df.lang == lang) & (da_df.metric.isin(PIVOT_METRICS))].dropna(subset=["spearman_r"])
        if sub.empty:
            continue
        best = sub.loc[sub.spearman_r.idxmax()]
        _pivot_winners[lang] = best.metric
        if best.metric == "metricx":
            metricx_wins += 1
    print(f"Pivot winners: {_pivot_winners}\n")
    add("PivotMetricXWins", metricx_wins, str(metricx_wins), "recompute:pivot", "MetricX overall-best count, pivot languages")
    add("PivotN", len(PIVOT_LANGS), str(len(PIVOT_LANGS)), "recompute:pivot", "n pivot languages")

    # Table 4 win-fraction and LOO-accuracy macros
    def best_of_three(lang, direction, kind="sep"):
        if kind == "sep":
            mx, ck, co = sep_rho(lang, direction, "metricx"), sep_rho(lang, direction, "cometkiwi23"), sep_rho(lang, direction, "comet")
        else:
            mx, ck, co = single_rho(lang, "metricx"), single_rho(lang, "cometkiwi23"), single_rho(lang, "comet")
        if mx is None or ck is None or co is None:
            return None, None, None, None
        best = max([("metricx", mx), ("cometkiwi23", ck), ("comet", co)], key=lambda x: x[1])[0]
        return best, mx, ck, co

    de_en_path = RESULTS / "scores_de_en.csv"
    de_en_scores = pd.read_csv(de_en_path) if de_en_path.exists() else None
    de_en_best = None
    if de_en_scores is not None:
        de_en_best = max(
            [("metricx", de_en_scores["metricx"].corr(de_en_scores["quality_score"], method="spearman")),
             ("cometkiwi23", de_en_scores["cometkiwi23"].corr(de_en_scores["quality_score"], method="spearman")),
             ("comet", de_en_scores["comet"].corr(de_en_scores["quality_score"], method="spearman"))],
            key=lambda x: x[1],
        )

    WIN_CELLS = {
        "XtoEnAgglutin": ([(l, "x_to_en", "sep") for l in AGGLUTIN_LANGS], "cometkiwi23"),
        "EntoXAgglutin": ([(l, "en_to_x", "sep") for l in AGGLUTIN_LANGS], "metricx"),
        # he is a standalone (non-mixed) X->en fusional language and was
        # missing from this count entirely (found via advisor review,
        # 2026-09-11): XTOEN_FUSIONAL_LANGS is built only from MIXED_LANGS,
        # which structurally excludes it. Added via kind="single" (reads
        # single_rho, not sep_rho) alongside de-en, which is added below the
        # same way for the same reason (also not in MIXED_LANGS).
        "XtoEnFusional": ([(l, "x_to_en", "sep") for l in XTOEN_FUSIONAL_LANGS]
                          + [("he", None, "single")], "cometkiwi23"),
        "EntoXFusional": ([(l, "en_to_x", "sep") for l in ENTOX_FUSIONAL_LANGS], "cometkiwi23"),
        "XtoEnIsolating": ([("km", "x_to_en", "sep"), ("zh", None, "single")], "metricx"),
    }
    for cell_name, (members, target_metric) in WIN_CELLS.items():
        wins, beats_comet, total = 0, 0, 0
        for lang, direction, kind in members:
            best, mx, ck, co = best_of_three(lang, direction, kind)
            if best is None:
                continue
            total += 1
            wins += (best == target_metric)
            beats_comet += (ck > co)
        if cell_name == "XtoEnFusional" and de_en_best is not None:
            total += 1
            wins += (de_en_best[0] == target_metric)
            de_en_ck23 = de_en_scores["cometkiwi23"].corr(de_en_scores["quality_score"], method="spearman")
            de_en_comet = de_en_scores["comet"].corr(de_en_scores["quality_score"], method="spearman")
            beats_comet += (de_en_ck23 > de_en_comet)
        add(f"Win{cell_name}", wins, str(wins), "recompute:table4_wins", f"{cell_name} win count")
        add(f"WinTotal{cell_name}", total, str(total), "recompute:table4_wins", f"{cell_name} total")
        add(f"BeatsComet{cell_name}", beats_comet, str(beats_comet), "recompute:table4_wins", f"{cell_name} CKXXIII>COMET count")

    # Bootstrap CIs on the CKXXIII>COMET win fraction per cell (Sec 4.5 text
    # and Table 4's dagger footnote).
    cell_ci_df = pd.read_csv(RESULTS / "direction_separated_cell_cis.csv")
    CELL_CI_NAMES = {
        ("agglutinative", "x_to_en"): "XtoEnAgglutin",
        ("agglutinative", "en_to_x"): "EntoXAgglutin",
        ("fusional", "en_to_x"): "EntoXFusional",
        ("fusional", "x_to_en"): "XtoEnFusional",
    }
    for (morph, direction), cell_name in CELL_CI_NAMES.items():
        row = cell_ci_df[(cell_ci_df.morphology == morph) & (cell_ci_df.direction == direction)]
        if row.empty:
            continue
        r = row.iloc[0]
        add(f"CellCI{cell_name}Lo", float(r.ci_lo), fmt2(r.ci_lo), "direction_separated_cell_cis.csv",
            f"{cell_name} bootstrap CI lower, CKXXIII>COMET win fraction")
        add(f"CellCI{cell_name}Hi", float(r.ci_hi), fmt2(r.ci_hi), "direction_separated_cell_cis.csv",
            f"{cell_name} bootstrap CI upper, CKXXIII>COMET win fraction")

    loo_df = pd.read_csv(RESULTS / "direction_separated_loo.csv")
    LOO_CELLS = {
        "XtoEnAgglutin": ("x_to_en", "agglutinative"), "EntoXAgglutin": ("en_to_x", "agglutinative"),
        "XtoEnFusional": ("x_to_en", "fusional"), "EntoXFusional": ("en_to_x", "fusional"),
    }
    for cell_name, (direction, morph) in LOO_CELLS.items():
        sub = loo_df[(loo_df.direction == direction) & (loo_df.morphology == morph)]
        correct, total = int(sub.loo_correct.sum()), len(sub)
        add(f"LOO{cell_name}", correct, str(correct), "recompute:loo", f"{cell_name} LOO correct")
        add(f"LOOTotal{cell_name}", total, str(total), "recompute:loo", f"{cell_name} LOO total")

    # Total direction-language pair observations across Table 4's 6 cells
    # (34, including de-en; 33 in the main pipeline alone).
    _table4_total = (
        stats["WinTotalXtoEnAgglutin"]["value"] + stats["WinTotalEntoXAgglutin"]["value"]
        + stats["WinTotalXtoEnFusional"]["value"] + stats["WinTotalEntoXFusional"]["value"]
        + stats["WinTotalXtoEnIsolating"]["value"] + stats["PivotN"]["value"]
    )
    add("TableFourTotalPairs", _table4_total, str(_table4_total), "recompute:table4",
        "Sum of Table 4's six cell n's, includes de-en held-out")
    add("TableFourMainPipelinePairs", _table4_total - 1, str(_table4_total - 1), "recompute:table4",
        "TableFourTotalPairs minus de-en (main-pipeline-only pair count)")

    # en->X total (agglutinative + fusional) and whether CK23 beats COMET in
    # every one of those pairs — the Sec 4.5 lead sentence's "13/13" claim.
    _entox_total = stats["WinTotalEntoXAgglutin"]["value"] + stats["WinTotalEntoXFusional"]["value"]
    _entox_beats_comet = stats["BeatsCometEntoXAgglutin"]["value"] + stats["BeatsCometEntoXFusional"]["value"]
    add("EntoXTotalPairs", _entox_total, str(_entox_total), "recompute:table4",
        "WinTotalEntoXAgglutin + WinTotalEntoXFusional")
    add("BeatsCometEntoXTotal", _entox_beats_comet, str(_entox_beats_comet), "recompute:table4",
        "BeatsCometEntoXAgglutin + BeatsCometEntoXFusional")

    # Overall LOO accuracy across the four cells large enough to validate
    # (isolating/pivot show "--" in Table 4, too small for LOO).
    _loo_valid_cells = ["XtoEnAgglutin", "EntoXAgglutin", "XtoEnFusional", "EntoXFusional"]
    _loo_correct_total = sum(stats[f"LOO{c}"]["value"] for c in _loo_valid_cells)
    _loo_total_total = sum(stats[f"LOOTotal{c}"]["value"] for c in _loo_valid_cells)
    add("LOOOverallCorrect", _loo_correct_total, str(_loo_correct_total), "recompute:loo",
        "Sum of LOO-correct across the 4 cells large enough to validate")
    add("LOOOverallTotal", _loo_total_total, str(_loo_total_total), "recompute:loo",
        "Sum of LOO totals across the 4 cells large enough to validate")
    add("LOOOverallPct", round(100 * _loo_correct_total / _loo_total_total), f"{round(100 * _loo_correct_total / _loo_total_total)}",
        "recompute:loo", "Overall LOO accuracy percentage")

    # Table 6/7 body: COMET + CKXXIII + MetricX rho, and n, for all 15 WMT DA
    # direction-separated languages.
    TABLE6_CELLS = [
        ("fi", "x_to_en"), ("et", "x_to_en"), ("tr", "x_to_en"), ("kk", "x_to_en"),
        ("ta", "x_to_en"), ("ja", "x_to_en"), ("ha", "x_to_en"),
        ("fi", "en_to_x"), ("et", "en_to_x"), ("kk", "en_to_x"), ("ta", "en_to_x"),
        ("tr", "en_to_x"), ("ja", "en_to_x"), ("ha", "en_to_x"),
        ("lt", "x_to_en"), ("cs", "x_to_en"), ("pl", "x_to_en"), ("gu", "x_to_en"),
        ("ps", "x_to_en"), ("is", "x_to_en"),
        ("lt", "en_to_x"), ("cs", "en_to_x"), ("pl", "en_to_x"), ("gu", "en_to_x"),
        ("is", "en_to_x"), ("lv", "en_to_x"),
    ]
    DIR_SUFFIX = {"x_to_en": "XE", "en_to_x": "EX"}
    for lang, direction in TABLE6_CELLS:
        for metric_name, metric_label in [("comet", "COMET"), ("cometkiwi23", "CKXXIII"), ("metricx", "MX")]:
            row = sep_df[(sep_df.lang == lang) & (sep_df.direction == direction) & (sep_df.metric == metric_name)]
            if row.empty:
                continue
            v = float(row.spearman_r.iloc[0])
            macro_name = f"SepMX{lang.upper()}{DIR_SUFFIX[direction]}" if metric_label == "MX" \
                else f"Sep{metric_label}{lang.upper()}{DIR_SUFFIX[direction]}"
            add(macro_name, v, fmt3(v), "recompute:table6", f"{lang} {direction} {metric_name}")
        n_row = sep_df[(sep_df.lang == lang) & (sep_df.direction == direction) & (sep_df.metric == "comet")]
        if len(n_row):
            n_val = int(n_row.n.iloc[0])
            add(f"SepN{lang.upper()}{DIR_SUFFIX[direction]}", n_val, fmt_n(n_val), "recompute:table6", f"{lang} {direction} n")

    # Ridge typological predictor (post-hoc check, Sec 4.5): Pearson r per
    # metric family and overall recommendation accuracy.
    predictor_summary_path = RESULTS / "predictor" / "summary.json"
    if predictor_summary_path.exists():
        with open(predictor_summary_path) as f:
            predictor_summary = json.load(f)
        ck23_r = predictor_summary["per_metric"]["cometkiwi23"]["lolo_pearson_r"]
        ck_r = predictor_summary["per_metric"]["cometkiwi"]["lolo_pearson_r"]
        add("RidgeCKXXIIIPearson", float(ck23_r), fmt2(ck23_r), "predictor/summary.json", "Ridge LOLO-CV Pearson r, CometKiwi23")
        add("RidgeCKPearson", float(ck_r), fmt2(ck_r), "predictor/summary.json", "Ridge LOLO-CV Pearson r, CometKiwi")
        add("RidgeRecAcc", predictor_summary["recommendation_accuracy"], predictor_summary["recommendation_accuracy"],
            "predictor/summary.json", "Ridge recommendation accuracy (best-metric prediction)")
        add("RidgeNLangs", predictor_summary["n_langs"], str(predictor_summary["n_langs"]),
            "predictor/summary.json", "Ridge predictor Tier-1 language count")
        # n_units is absent from summaries written before 2026-11-09; pass 1 of
        # the regen runs before the predictor is rebuilt, so tolerate it there.
        if "n_units" in predictor_summary:
            add("RidgeNUnits", predictor_summary["n_units"], str(predictor_summary["n_units"]),
                "predictor/summary.json",
                "Ridge units: single-direction languages + one unit per direction for mixed languages")

    # Max |MetricX - CKXXIII| margin among kk/tr (Table 4 caption's "advantage
    # often <X" claim) -- the two smallest agglutinative en_to_x margins.
    kk_tr_margin = max(
        abs(sep_rho("kk", "en_to_x", "metricx") - sep_rho("kk", "en_to_x", "cometkiwi23")),
        abs(sep_rho("tr", "en_to_x", "metricx") - sep_rho("tr", "en_to_x", "cometkiwi23")),
    )
    add("KkTrMaxMargin", kk_tr_margin, fmt3(kk_tr_margin), "direction_separated_correlations.csv",
        "Max |MetricX-CKXXIII| margin among kk/tr, agglutinative en_to_x")

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 3: Year-stratified (Table 5) + held-out de-en pair
    # (formerly generate_yearstrat_macros.py)
    # ─────────────────────────────────────────────────────────────────────
    tier_anomaly_df = pd.read_csv(RESULTS / "tier_anomaly.csv")
    tier_anomaly_df = tier_anomaly_df[tier_anomaly_df.metric == "comet"]

    YEAR_STRAT_ENTRIES = [
        ("ru", 2021, "RuWmtOneRho", "RuWmtOneN"), ("ru", 2022, "RuWmtTwoRho", "RuWmtTwoN"),
        ("de", 2020, "DeWmtTwoZeroRho", None), ("de", 2021, "DeWmtTwoOneRho", None), ("de", 2022, "DeWmtTwoTwoRho", None),
    ]
    for lang, year, rho_macro, n_macro in YEAR_STRAT_ENTRIES:
        row = tier_anomaly_df[(tier_anomaly_df.lang == lang) & (tier_anomaly_df.year.astype(str) == f"{float(year)}")]
        if row.empty:
            raise SystemExit(f"Missing tier_anomaly.csv row for {lang} {year}")
        r = row.iloc[0]
        add(rho_macro, float(r.year_spearman_r), fmt_rho(r.year_spearman_r), "tier_anomaly.csv",
            f"{lang} WMT{year} COMET rho, n={int(r.n)}")
        if n_macro:
            add(n_macro, int(r.n), fmt_n(r.n), "tier_anomaly.csv", f"{lang} WMT{year} segment count")

    RANGE_ENTRIES = [("ru", "RuRange", "RuDelta"), ("de", "DeRange", "DeDelta"), ("zh", "ZhRange", "ZhDelta")]
    for lang, range_macro, delta_macro in RANGE_ENTRIES:
        sub = tier_anomaly_df[tier_anomaly_df.lang == lang]
        if sub.empty:
            raise SystemExit(f"No tier_anomaly.csv rows for {lang}")
        yr_vals = sub["year_spearman_r"]
        agg = float(sub["aggregate_spearman_r"].iloc[0])
        lo, hi = float(yr_vals.min()), float(yr_vals.max())
        delta = float(yr_vals.mean()) - agg
        add(f"{range_macro}Lo", lo, fmt2(lo), "tier_anomaly.csv", f"{lang} year rho min")
        add(f"{range_macro}Hi", hi, fmt2(hi), "tier_anomaly.csv", f"{lang} year rho max")
        add(delta_macro, delta, fmt_signed3(delta), "tier_anomaly.csv", f"{lang} stratified mean - pooled")

    cs_path = RESULTS / "simpsons_cs_da.csv"
    if cs_path.exists():
        cs = pd.read_csv(cs_path)
        cs_xe = cs[(cs.lang == "cs") & (cs.direction == "x_to_en")]
        yr_vals = cs_xe["year_spearman_r"]
        pooled = float(cs_xe["pooled_spearman_r"].iloc[0])
        lo, hi = float(yr_vals.min()), float(yr_vals.max())
        delta = float(yr_vals.mean()) - pooled
        add("CsEnPooled", pooled, fmt_rho(pooled), "simpsons_cs_da.csv", "cs-en (x_to_en) pooled COMET rho")
        add("CsEnRangeLo", lo, fmt2(lo), "simpsons_cs_da.csv", "cs-en year rho min")
        add("CsEnRangeHi", hi, fmt2(hi), "simpsons_cs_da.csv", "cs-en year rho max")
        add("CsEnDelta", delta, fmt_signed3(delta), "simpsons_cs_da.csv", "cs-en stratified mean - pooled")

    if de_en_scores is not None:
        q = de_en_scores["quality_score"]
        comet_r, _ = spearmanr(q, de_en_scores["comet"])
        kiwi_r, _ = spearmanr(q, de_en_scores["cometkiwi23"])
        metricx_r, _ = spearmanr(q, de_en_scores["metricx"])
        n = len(de_en_scores)
        add("DeEnCOMETRho", float(comet_r), fmt_rho(comet_r), "scores_de_en.csv", f"de-en held-out, n={n}")
        add("DeEnKiwiRho", float(kiwi_r), fmt_rho(kiwi_r), "scores_de_en.csv", f"de-en held-out, n={n}")
        add("DeEnMetricXRho", float(metricx_r), fmt_rho(metricx_r), "scores_de_en.csv", f"de-en held-out, n={n}")
        # Table 8 needs the leading-zero style (fmt3) to match the \SepCOMET*/
        # \SepCKXXIII* cells in the same column -- fmt_rho rendered de-en's
        # row as ".383"/".414" while every other row showed "0.xxx". Separate
        # macros rather than reformatting the above, which are also used
        # inline in prose matching that convention's no-leading-zero style.
        add("DeEnCOMETRhoTbl", float(comet_r), fmt3(comet_r), "scores_de_en.csv", f"de-en held-out, n={n} (Table 8 cell)")
        add("DeEnKiwiRhoTbl", float(kiwi_r), fmt3(kiwi_r), "scores_de_en.csv", f"de-en held-out, n={n} (Table 8 cell)")
        add("DeEnN", n, fmt_n(n), "scores_de_en.csv", "de-en held-out segment count")

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 4: Hebrew score-discrimination (Cohen's d, quality-bucket means)
    # (formerly generate_hebrew_discrimination_macros.py)
    #
    # This used to only exist inside a matplotlib figure title in
    # make_presentation_plots.py:plot_score_discrimination() — never saved
    # anywhere, so the paper's 0.51/1.45 had nothing to trace to, and a stale
    # docstring in that same function claimed different values (~0.47/~1.73)
    # for the same fact. Reproduces that function's core computation (no
    # plotting), saves it to results/hebrew_discrimination.csv (which the
    # plotting function now reads instead of recomputing), so the figure and
    # the paper can't drift.
    # ─────────────────────────────────────────────────────────────────────
    surf = pd.read_csv(RESULTS / "surface_similarity.csv")

    # chrF for error-free (MQM=0) segments, Hebrew vs German — rules out
    # surface dissimilarity as the explanation for Hebrew's COMET collapse.
    for _lang, _label in [("he", "HE"), ("de", "DE")]:
        _errorfree_chrf = float(surf[(surf.lang == _lang) & (surf.mqm_score == 0)].chrf.mean())
        add(f"ChrFErrorFree{_label}", _errorfree_chrf, fmt2(_errorfree_chrf), "surface_similarity.csv",
            f"{_lang} mean chrF for error-free (MQM=0) segments")

    # he_surf's segment_id ("he_<system>_<globalSegId>") was built from a
    # standalone script's own numbering and no longer matches the segment_id
    # scheme scores_comet.csv/scores_cometkiwi.csv use after the reference-fix
    # (found via advisor review, 2026-09-11): the join silently produced 0
    # rows, so every Cohen's d here was NaN. Rebuild the MQM quality bucketing
    # from the same corrected span+ref-lookup path as _build_span_lang_correct_rows
    # above, which is guaranteed to produce a segment_id consistent with the
    # checkpoint CSVs.
    he_df = load_span_fallback_scores(Path(mqm_settings.data.wmt_mqm_span_dir), [_SPAN_LANG_SPECS["he"]["lp"]])
    he_df["mqm_score"] = -he_df["error_penalty"]
    _he_comet_df = pd.read_csv(RESULTS / "scores_comet.csv")[["segment_id", "comet"]]
    _he_kiwi_df = pd.read_csv(RESULTS / "scores_cometkiwi.csv")[["segment_id", "cometkiwi"]]
    he_df = he_df.merge(_he_comet_df, on="segment_id", how="inner").merge(_he_kiwi_df, on="segment_id", how="inner")

    _quality_order = ["poor", "medium", "perfect"]
    he_df["quality"] = pd.cut(he_df["mqm_score"], bins=[-999, -5, -1, 0.001], labels=_quality_order)
    he_df = he_df.dropna(subset=["quality"])

    _he_disc_rows = []
    for col, label in [("comet", "Comet"), ("cometkiwi", "Kiwi")]:
        g_perf = he_df[he_df["quality"] == "perfect"][col].dropna()
        g_poor = he_df[he_df["quality"] == "poor"][col].dropna()
        pooled_std = np.sqrt((g_perf.std() ** 2 + g_poor.std() ** 2) / 2)
        d = (g_perf.mean() - g_poor.mean()) / pooled_std
        overall_mean, overall_std = he_df[col].mean(), he_df[col].std()
        _he_disc_rows.append({
            "metric": col, "n_perfect": len(g_perf), "n_poor": len(g_poor),
            "perfect_mean": g_perf.mean(), "poor_mean": g_poor.mean(),
            "cohens_d": d, "overall_mean": overall_mean, "overall_std": overall_std,
        })
        add(f"HeCohensD{label}", float(d), fmt2(d), "hebrew_discrimination", f"Cohen's d, Hebrew {col}, perfect vs poor MQM bucket")

    pd.DataFrame(_he_disc_rows).to_csv(RESULTS / "hebrew_discrimination.csv", index=False)
    print(f"Wrote {RESULTS / 'hebrew_discrimination.csv'}")

    # z-score: CSV-backed value from abjad_score_distributions.csv. The paper's
    # original "7.5 sigma" claim could not be reproduced under any plausible
    # methodology tried (best reproduction tops out ~4.5 sigma) and is treated
    # as an unsourced/incorrect legacy claim; this replaces it.
    _abjad = pd.read_csv(RESULTS / "abjad_score_distributions.csv")
    _he_row = _abjad[_abjad.lang == "he"].iloc[0]
    add("HeZScore", float(abs(_he_row.z_score)), fmt2(abs(_he_row.z_score)), "abjad_score_distributions.csv",
        "Hebrew COMET z-score vs cross-language per-segment mean")

    # Full-dataset (not MQM-bucket-restricted) Hebrew mean/std — the "COMET-22
    # assigns a mean score of 0.423 (sigma=0.048)... Kiwi-22 a normal mean
    # score of 0.778" claim, distinct from the perfect/poor bucket means above
    # (a smaller subset restricted to segments with a valid MQM quality label).
    add("HeFullMeanComet", float(_he_row.comet_mean), fmt3(_he_row.comet_mean), "abjad_score_distributions.csv",
        "Hebrew full-dataset COMET-22 mean score")
    add("HeFullStdComet", float(_he_row.comet_std), fmt3(_he_row.comet_std), "abjad_score_distributions.csv",
        "Hebrew full-dataset COMET-22 std")
    _he_kiwi_full = pd.read_csv(RESULTS / "scores_cometkiwi.csv")
    _he_kiwi_full_mean = float(_he_kiwi_full[_he_kiwi_full.lang == "he"].cometkiwi.mean())
    add("HeFullMeanKiwi", _he_kiwi_full_mean, fmt3(_he_kiwi_full_mean), "scores_cometkiwi.csv",
        "Hebrew full-dataset COMET-Kiwi-22 mean score")

    # External validation: corrected he-en/en-es checkpoints for all four
    # previously-buggy metrics (COMET, BLEURT, xCOMET, MetricX), compared at
    # SEGMENT level against the official WMT23/WMT24 mt-metrics-eval-v2
    # per-(system, segment) baseline scores -- see
    # scripts/validate_against_mt_metrics_eval.py. Advisor review
    # (2026-09-12) correctly flagged an earlier draft's SYSTEM-level version
    # of this check (correlating ~12-14 system means) as too forgiving a
    # test to catch a segment-alignment bug; this is the same-named macro
    # family recomputed the rigorous way, not a second, laxer methodology
    # kept alongside it.
    _baseline_val = pd.read_csv(RESULTS / "wmt_baseline_validation_segment_level.csv")
    add("BaselineValNChecks", len(_baseline_val), str(len(_baseline_val)), "wmt_baseline_validation_segment_level.csv",
        "Number of (language, metric) external-baseline validation checks run")
    _min_pearson_row = _baseline_val.loc[_baseline_val.pearson_r.idxmin()]
    _min_spearman_row = _baseline_val.loc[_baseline_val.spearman_r.idxmin()]
    add("BaselineValMinPearson", float(_min_pearson_row.pearson_r), fmt3(_min_pearson_row.pearson_r),
        "wmt_baseline_validation_segment_level.csv",
        f"Weakest segment-level Pearson r across all external-baseline validation checks "
        f"(lang={_min_pearson_row.lang}, metric={_min_pearson_row.metric})")
    add("BaselineValMinSpearman", float(_min_spearman_row.spearman_r), fmt3(_min_spearman_row.spearman_r),
        "wmt_baseline_validation_segment_level.csv",
        f"Weakest segment-level Spearman r across all external-baseline validation checks "
        f"(lang={_min_spearman_row.lang}, metric={_min_spearman_row.metric})")
    # COMET and xCOMET specifically (the two metrics underpinning the Hebrew/
    # Spanish reversal finding in \S\ref{sec:per_lang}) checkpoint-match the
    # official baseline exactly; report their segment-level agreement
    # separately from BLEURT/MetricX, whose weaker agreement traces to a
    # genuine checkpoint-version difference (see BaselineValCheckpointNote).
    _core_val = _baseline_val[_baseline_val.metric.isin(["comet", "xcomet"])]
    _core_min_pearson = float(_core_val.pearson_r.min())
    _core_min_spearman = float(_core_val.spearman_r.min())
    add("BaselineValCoreMinPearson", _core_min_pearson, fmt3(_core_min_pearson),
        "wmt_baseline_validation_segment_level.csv",
        "Weakest segment-level Pearson r for COMET/xCOMET only (checkpoint-matched to the official baseline)")
    add("BaselineValCoreMinSpearman", _core_min_spearman, fmt3(_core_min_spearman),
        "wmt_baseline_validation_segment_level.csv",
        "Weakest segment-level Spearman r for COMET/xCOMET only (checkpoint-matched to the official baseline)")

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 5: Mixed-effects robustness check (WMT26 Reviewer 2, Q1/Q2/Q6)
    #
    # The headline eta^2_dir/eta^2_morph ANOVA (Section 2) treats each
    # (language, direction) row as independent, but the 12 MIXED_LANGS
    # contribute two correlated rows each (one per direction) from the same
    # underlying language. This fits a linear mixed-effects model with
    # language as a random intercept to check whether direction and
    # morphology remain significant predictors once that non-independence is
    # modeled explicitly instead of assumed away — the exact model the
    # reviewer requested. Reported as a robustness subsection, not a
    # replacement for the ANOVA (different models answer slightly different
    # questions; both are disclosed).
    # ─────────────────────────────────────────────────────────────────────
    import statsmodels.formula.api as smf

    def _base_lang(lang: str) -> str:
        for suffix in ("_x_t", "_en_"):
            if lang.endswith(suffix):
                return lang[: -len(suffix)]
        return lang

    _lmm_df = build_corrected_lang_dir_rho("comet").dropna(subset=["spearman_r"]).copy()
    _lmm_df["base_lang"] = _lmm_df["lang"].apply(_base_lang)
    _lmm_model = smf.mixedlm("spearman_r ~ C(direction) + C(morphology)", data=_lmm_df, groups=_lmm_df["base_lang"])
    _lmm_result = _lmm_model.fit(reml=True)

    add("MixedModelNObs", len(_lmm_df), str(len(_lmm_df)), "recompute:mixed_effects", "LMM observation count")
    add("MixedModelNLangs", int(_lmm_df["base_lang"].nunique()), str(int(_lmm_df["base_lang"].nunique())),
        "recompute:mixed_effects", "LMM unique-language count (random-effect groups)")

    _dir_xtoen_coef = float(_lmm_result.params["C(direction)[T.x_to_en]"])
    _dir_xtoen_p = float(_lmm_result.pvalues["C(direction)[T.x_to_en]"])
    _morph_fus_coef = float(_lmm_result.params["C(morphology)[T.fusional]"])
    _morph_fus_p = float(_lmm_result.pvalues["C(morphology)[T.fusional]"])
    _icc = float(_lmm_result.cov_re.iloc[0, 0] / (_lmm_result.cov_re.iloc[0, 0] + _lmm_result.scale))

    add("MixedModelDirXtoEnCoef", _dir_xtoen_coef, fmt_signed3(_dir_xtoen_coef), "recompute:mixed_effects",
        "LMM fixed effect: X->en vs en->X (reference), controlling for morphology, language random intercept")
    add("MixedModelDirXtoEnP", _dir_xtoen_p, fmt_pval(_dir_xtoen_p), "recompute:mixed_effects",
        "LMM p-value for X->en direction effect")
    add("MixedModelMorphFusionalCoef", _morph_fus_coef, fmt_signed3(_morph_fus_coef), "recompute:mixed_effects",
        "LMM fixed effect: fusional vs agglutinative (reference), controlling for direction, language random intercept")
    add("MixedModelMorphFusionalP", _morph_fus_p, fmt3(_morph_fus_p), "recompute:mixed_effects",
        "LMM p-value for fusional morphology effect")
    add("MixedModelICC", _icc, fmt2(_icc), "recompute:mixed_effects",
        "Intraclass correlation: fraction of variance from the language random intercept")

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 6: Year-stratification robustness check (WMT26 Reviewer 3)
    #
    # Only de, ru, zh, cs are multi-year in the direction x morphology cell
    # data; every other language contributing to Table 2 is single-year. de
    # and ru's en->X-fusional cell membership uses their POOLED (not
    # year-stratified) rho, which Sec 5.3 already shows is a Simpson's-
    # Paradox-suppressed value for ru specifically. Substitute each language's
    # mean-of-per-year rho for its pooled rho in that cell and recompute the
    # cell mean to check whether the direction effect survives.
    # ─────────────────────────────────────────────────────────────────────
    _entox_fus_pooled = build_corrected_lang_dir_rho("comet")
    _entox_fus_pooled = _entox_fus_pooled[(_entox_fus_pooled["direction"] == "en_to_x")
                                           & (_entox_fus_pooled["morphology"] == "fusional")]
    _de_strat = (stats["DeWmtTwoZeroRho"]["value"] + stats["DeWmtTwoOneRho"]["value"] + stats["DeWmtTwoTwoRho"]["value"]) / 3
    _ru_strat = (stats["RuWmtOneRho"]["value"] + stats["RuWmtTwoRho"]["value"]) / 2
    _strat_vals = _entox_fus_pooled["spearman_r"].copy()
    _strat_vals[_entox_fus_pooled["lang"] == "de"] = _de_strat
    _strat_vals[_entox_fus_pooled["lang"] == "ru"] = _ru_strat
    _pooled_cell_mean = float(_entox_fus_pooled["spearman_r"].mean())
    _strat_cell_mean = float(_strat_vals.mean())
    add("YearStratEntoXFusionalPooled", _pooled_cell_mean, fmt3(_pooled_cell_mean), "recompute:year_strat_robustness",
        "en_to_x x fusional cell mean COMET rho, using pooled (not year-stratified) de/ru values")
    add("YearStratEntoXFusionalStrat", _strat_cell_mean, fmt3(_strat_cell_mean), "recompute:year_strat_robustness",
        "en_to_x x fusional cell mean COMET rho, de/ru replaced with their mean-of-per-year rho")

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 7: Tier 1b protocol-controlled resource-level check
    #
    # Annotation protocol and resource tier are perfectly confounded across
    # Tier 1a (MQM, high) vs Tier 1b (DA, medium/low) -- unfixable with this
    # data (no language has both). But WITHIN Tier 1b, medium and low are
    # both DA-annotated, so protocol is held constant there. Check whether
    # resource level predicts reliability in that one protocol-controlled
    # subset, across all metrics, excluding the domain-confounded uk and
    # excluding ha (whose X->en near-zero score is already independently
    # documented as annotation noise, not signal, in Table 7's own caption).
    # ─────────────────────────────────────────────────────────────────────
    _da_only = corr_df[(corr_df.annotation_tier == "human_da")
                        & (corr_df.resource_tier.isin(["medium", "low"]))
                        & (corr_df.lang != "uk")]
    _low_mean = float(_da_only[_da_only.resource_tier == "low"]["spearman_r"].mean())
    _med_mean = float(_da_only[_da_only.resource_tier == "medium"]["spearman_r"].mean())
    _low_ex_ha_mean = float(_da_only[(_da_only.resource_tier == "low") & (_da_only.lang != "ha")]["spearman_r"].mean())
    add("TierOneBLowMean", _low_mean, fmt3(_low_mean), "recompute:tier1b_check",
        "Tier 1b (DA-only) low-resource mean rho across all metrics, uk excluded")
    add("TierOneBMedMean", _med_mean, fmt3(_med_mean), "recompute:tier1b_check",
        "Tier 1b (DA-only) medium-resource mean rho across all metrics, uk excluded")
    add("TierOneBLowExHaMean", _low_ex_ha_mean, fmt3(_low_ex_ha_mean), "recompute:tier1b_check",
        "Tier 1b (DA-only) low-resource mean rho, ha additionally excluded (documented annotation-noise outlier)")

    # ─────────────────────────────────────────────────────────────────────
    # MQM CONTROL (corrected paper v2, 2026-11-10). Same-year en->X minus
    # X->en COMET gap under expert MQM vs WMT DA, on identical segment sets.
    # Source: scripts/audit/mqm_control.py and followup_analyses.py, which read
    # official mt-metrics-eval-v2 files only (no mqmbench loader code), so the
    # 2026-11-09 label fixes cannot affect them. The point gaps are recomputed
    # here from mqm_control.csv and must match the bootstrap file's points.
    # ─────────────────────────────────────────────────────────────────────
    _ctrl = pd.read_csv(RESULTS / "mqm_control.csv")
    _ci = pd.read_csv(RESULTS / "followup_bootstrap_ci.csv")
    _ci_gap = _ci[_ci.direction == "gap"]
    if _ci_gap.empty:
        raise SystemExit("followup_bootstrap_ci.csv has no gap rows; rerun scripts/audit/followup_analyses.py")
    _YEAR_WORD = {"wmt20": "Twenty", "wmt21.news": "TwentyOne", "wmt22": "TwentyTwo", "wmt23": "TwentyThree"}
    _LABEL_WORD = {"COMET~MQM": "MQM", "COMET~DA": "DA"}
    _n_gap_ci_excl_zero = {"MQM": 0, "DA": 0}
    _n_gap = {"MQM": 0, "DA": 0}
    _mqm_gap_signs = []
    for _ts, _yw in _YEAR_WORD.items():
        _y = _ctrl[_ctrl.testset == _ts]
        for _stat, _lw in _LABEL_WORD.items():
            _e = _y[_y.direction == "en_to_x"][_stat].dropna()
            _x = _y[_y.direction == "x_to_en"][_stat].dropna()
            if _e.empty or _x.empty:
                continue
            _pt = float(_e.mean() - _x.mean())
            _row = _ci_gap[(_ci_gap.testset == _ts) & (_ci_gap.stat == _stat)]
            if len(_row) != 1 or abs(float(_row.point.iloc[0]) - _pt) > 1e-9:
                raise SystemExit(f"MQM control gap {_ts} {_stat}: point {_pt} does not match bootstrap file")
            _lo, _hi = float(_row.lo.iloc[0]), float(_row.hi.iloc[0])
            add(f"MqmCtrlGap{_lw}{_yw}", _pt, fmt_signed3(_pt), "mqm_control.csv",
                f"{_ts}: mean en->X minus mean X->en COMET Spearman under {_lw}")
            add(f"MqmCtrlGap{_lw}{_yw}CIlo", _lo, fmt_signed3(_lo), "followup_bootstrap_ci.csv",
                f"{_ts} {_lw} gap, 95% CI low (1000 resamples of source segments)")
            add(f"MqmCtrlGap{_lw}{_yw}CIhi", _hi, fmt_signed3(_hi), "followup_bootstrap_ci.csv",
                f"{_ts} {_lw} gap, 95% CI high")
            _n_gap[_lw] += 1
            _n_gap_ci_excl_zero[_lw] += int(_lo > 0 or _hi < 0)
            if _lw == "MQM":
                _mqm_gap_signs.append(_pt > 0)
    for _lw in ("MQM", "DA"):
        add(f"MqmCtrlNYears{_lw}", _n_gap[_lw], str(_n_gap[_lw]), "mqm_control.csv",
            f"Number of WMT years with a same-year {_lw} direction gap")
        add(f"MqmCtrlNCIExclZero{_lw}", _n_gap_ci_excl_zero[_lw], str(_n_gap_ci_excl_zero[_lw]),
            "followup_bootstrap_ci.csv", f"Years whose {_lw} gap CI excludes zero")
    _n_neg = int(sum(not s for s in _mqm_gap_signs))
    add("MqmCtrlNNegMQM", _n_neg, str(_n_neg), "mqm_control.csv",
        "Years in which the MQM gap is negative (X->en better evaluated than en->X)")
    _n_pairs = int(_ctrl.lp.nunique())
    add("MqmCtrlNPairs", _n_pairs, str(_n_pairs), "mqm_control.csv",
        "Language pairs with expert MQM in the control (en-de, en-ru, zh-en, he-en)")
    _tri = pd.read_csv(RESULTS / "mqm_control_three_labels.csv").set_index("label")
    for _lab, _w in (("MQM", "MQM"), ("DA", "CrowdDA"), ("DA-appraise", "SrcDA")):
        _v = float(_tri.loc[_lab, "COMET"])
        add(f"MqmCtrlZhTwentyTwoCOMET{_w}", _v, fmt_rho(_v), "mqm_control_three_labels.csv",
            f"WMT22 zh-en COMET Spearman vs {_lab} labels, identical segment set")
    _ntri = int(_tri["n"].iloc[0])
    add("MqmCtrlZhTwentyTwoN", _ntri, fmt_n(_ntri), "mqm_control_three_labels.csv",
        "WMT22 zh-en segments with all three label types")

    # ─────────────────────────────────────────────────────────────────────
    # WRITE paper_stats.json
    #
    # This script is the ONLY generator of computed stats, so it doesn't need
    # read-merge-write's complexity: the stats dict built above is complete
    # and deterministic every run. Overwriting wholesale (rather than
    # merging) means there is no such thing as a stale leftover key from a
    # previous run's now-renamed or now-removed macro.
    # ─────────────────────────────────────────────────────────────────────
    json_path = RESULTS / "paper_stats.json"
    json_out = {k: {"value": v["value"], "fmt": v["fmt"], "source": v["source"], "note": v["note"]}
                for k, v in stats.items()}
    with open(json_path, "w") as f:
        json.dump(json_out, f, indent=2, default=str, sort_keys=True)
    print(f"\nWrote {len(json_out)} entries -> {json_path}")

    manual_keys = [k for k, v in stats.items() if v["source"].startswith("manual")]
    if manual_keys:
        print(f"\nManual entries ({len(manual_keys)}) - not sourced from a CSV:")
        for k in manual_keys:
            print(f"  {k}: {stats[k]['value']}  # {stats[k]['note']}")


if __name__ == "__main__":
    main()
