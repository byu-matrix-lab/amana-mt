"""Main evaluation pipeline for public datasets.

Steps:
    1. Load Tier 1a (WMT MQM), Tier 1b (WMT DA), Tier 2 (FLORES + NLLB + synthetic MQM)
    2. Convert span-level annotations to sentence scores where applicable
    3. Run configured MT metrics across all tiers
    4. Compute correlations against human/synthetic quality scores
    5. Generate plots and save results
"""

import gc
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from mqmbench.analysis.correlation import (
    analyze_metric_disagreements,
    analyze_tier_anomaly,
    compute_metric_correlations,
    kiwi_vs_comet_by_tier,
    reference_quality_effect,
    run_correlation_analysis,
    run_direction_analysis,
    run_direction_morphology_interaction,
    run_domain_analysis,
    run_domain_controlled_comparison,
    run_length_analysis,
    run_morphology_analysis,
    run_rater_agreement_analysis,
    run_system_level_analysis,
    run_williams_tests,
    summarize_by_family,
    summarize_by_script,
    summarize_by_tier,
)
from mqmbench.analysis.plots import (
    plot_correlation_by_language_family,
    plot_correlation_by_resource_level,
    plot_correlation_by_script_type,
    plot_direction_analysis,
    plot_domain_analysis,
    plot_kiwi_vs_comet_by_tier,
    plot_length_analysis,
    plot_metric_category_heatmap,
    plot_metric_correlation_matrix,
    plot_morphology_analysis,
    plot_nontranslation_detection,
    plot_rater_agreement_analysis,
    plot_reference_quality_effect,
    plot_score_distributions,
    plot_system_vs_segment_correlation,
    plot_tier_anomaly,
)
from mqmbench.config import init_settings, settings
from mqmbench.constants import AnnotationTier
from mqmbench.data.converter import annotations_to_sentence_scores  # used for Tier 2 synthetic spans
from mqmbench.data.flores import load_flores
from mqmbench.data.nllb import generate_hypotheses
from mqmbench.data.synthetic_mqm import generate_synthetic_mqm
from mqmbench.data.wmt_da import load_wmt_da
from mqmbench.data.wmt_mqm import (
    build_sacrebleu_ref_lookup, load_wmt_mqm, load_wmt_mqm_spans, _SACREBLEU_OFFSETS,
)

logger = logging.getLogger(__name__)


def run_pipeline(
    settings_file: Optional[str] = None,
    only_metrics: Optional[list[str]] = None,
    analysis_only: bool = False,
) -> Optional[dict]:
    """Run the full benchmark pipeline.

    Args:
        settings_file: Path to settings TOML (overrides default).
        only_metrics: If set, override metrics.run with this list. Use to run
            one metric per SLURM job to avoid MaxRSS accumulation across models.
        analysis_only: If True, skip metric computation entirely and just load
            the existing checkpoint then run correlation analysis.
    """
    if settings_file:
        init_settings(settings_file)

    output_dir = Path(settings.data.results_dir)
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    cache_dir = settings.data.cache_dir
    all_scores = []

    logger.info("=== Tier 1a: WMT MQM ===")
    # RicardoRei/wmt-mqm-human-evaluation provides sentence-level scores directly;
    # no span conversion needed. Category analysis is not available from this source.
    mqm_scores_df = load_wmt_mqm(lang_pairs=list(settings.data.wmt_mqm_pairs))
    if not mqm_scores_df.empty:
        all_scores.append(mqm_scores_df)
        logger.info(f"  {len(mqm_scores_df)} segments, languages: {sorted(mqm_scores_df['lang'].unique())}")

    hf_langs = set(mqm_scores_df["lang"].unique()) if not mqm_scores_df.empty else set()
    from mqmbench.data.utils import lang_from_pair
    span_dir = Path(getattr(settings.data, "wmt_mqm_span_dir", ""))
    missing_langs = {lang_from_pair(lp) for lp in settings.data.wmt_mqm_pairs} - hf_langs

    logger.info("=== Tier 1b: WMT DA ===")
    da_scores_df = load_wmt_da(target_langs=list(settings.data.wmt_da_target_langs))
    if not da_scores_df.empty:
        all_scores.append(da_scores_df)
        logger.info(f"  {len(da_scores_df)} segments, languages: {sorted(da_scores_df['lang'].unique())}")

    logger.info("=== Tier 2: Synthetic MQM ===")
    tier2_langs = list(getattr(settings.data, "tier2_langs", []))
    if tier2_langs:
        # Try to load FLORES+ source/reference text. If unavailable (e.g. gated
        # dataset after cache wipe), fall back to reading directly from the NLLB
        # hypothesis cache files which already contain source + reference text.
        try:
            flores_df = load_flores(lang_codes=tier2_langs)
        except Exception as e:
            logger.warning(f"FLORES+ unavailable ({e}); loading Tier 2 from NLLB cache directly.")
            flores_df = pd.DataFrame()

        if not flores_df.empty:
            flores_hyp_df = generate_hypotheses(
                flores_df, model_name=settings.data.nllb_model, cache_dir=cache_dir,
            )
        else:
            # Load hypotheses, source and reference directly from NLLB JSONL cache
            from mqmbench.data.utils import read_jsonl_cache
            from pathlib import Path as _Path
            hyp_rows = []
            for lang in tier2_langs:
                cache_file = _Path(cache_dir) / f"nllb_hypotheses_{lang}.jsonl"
                if cache_file.exists():
                    hyp_rows.extend(read_jsonl_cache(cache_file))
                else:
                    logger.warning(f"No NLLB cache for {lang} — skipping.")
            flores_hyp_df = pd.DataFrame(hyp_rows) if hyp_rows else pd.DataFrame()

        synth_model = settings.metrics.gemba_model
        if flores_hyp_df.empty:
            logger.warning("No Tier 2 hypothesis data available — skipping synthetic MQM.")
        elif not synth_model:
            logger.warning("metrics.gemba_model not set — skipping Tier 2 synthetic MQM.")
        else:
            synth_raw_df = generate_synthetic_mqm(
                flores_hyp_df, model_name=synth_model, cache_dir=cache_dir,
            )
            synth_scores_df = annotations_to_sentence_scores(synth_raw_df)
            synth_scores_df["annotation_tier"] = AnnotationTier.SYNTHETIC_MQM
            all_scores.append(synth_scores_df)
            logger.info(f"  {len(synth_scores_df)} segments, languages: {sorted(synth_scores_df['lang'].unique())}")

    # Fall back to span TSV for MQM pairs absent from the HF dataset (e.g. he-en, en-es).
    # Appended AFTER Tier2 so that the row ordering of [MQM_HF, DA, Tier2] remains
    # consistent with existing checkpoint CSVs — positional alignment is valid for
    # those tiers, and the fallback rows are a clean suffix that can be merged or filled.
    if missing_langs and span_dir and span_dir.exists():
        missing_pairs = [lp for lp in settings.data.wmt_mqm_pairs
                         if lang_from_pair(lp) in missing_langs]
        logger.info(f"  Loading span TSVs for HF-missing pairs: {sorted(missing_langs)}")

        # Build sacreBLEU reference lookups so that reference-based metrics work.
        # Lookups are keyed by lang code (e.g. "he", "es"); offsets are hardcoded
        # in _SACREBLEU_OFFSETS per (testset, lang_pair). Silently skip on failure
        # (compute nodes may lack internet, but the file should be cached already).
        _WMT_YEAR = {"he-en": "wmt23", "en-es": "wmt24"}
        ref_lookups: dict[str, dict[int, str]] = {}
        for lp in missing_pairs:
            testset = _WMT_YEAR.get(lp)
            if testset is None:
                continue
            offset = _SACREBLEU_OFFSETS.get((testset, lp), 0)
            lookup = build_sacrebleu_ref_lookup(lp, testset, global_seg_id_offset=offset)
            if lookup:
                lang_code = lang_from_pair(lp)
                ref_lookups[lang_code] = lookup
                logger.info(f"    Built ref lookup for {lp}: {len(lookup)} entries")

        fallback_spans = load_wmt_mqm_spans(
            span_dir,
            lang_pairs=missing_pairs,
            ref_lookups=ref_lookups or None,
        )
        if not fallback_spans.empty:
            fallback_scores = annotations_to_sentence_scores(fallback_spans)
            fallback_scores["annotation_tier"] = AnnotationTier.HUMAN_MQM
            all_scores.append(fallback_scores)
            logger.info(f"  Span fallback: {len(fallback_scores)} segments, "
                        f"languages: {sorted(fallback_scores['lang'].unique())}")

    if not all_scores:
        raise RuntimeError("No data loaded from any tier. Check settings and network access.")

    # Tier 2 synthetic MQM may have loaded a large LLM (Llama) to generate annotations.
    # Explicitly free it before loading neural MT metrics to avoid OOM.
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

    full_scores_df = pd.concat(all_scores, ignore_index=True)

    if analysis_only:
        logger.info("=== Analysis-only mode: loading per-metric checkpoints ===")
        metric_columns = []
        for metric_path in sorted(output_dir.glob("scores_*.csv")):
            metric = metric_path.stem[len("scores_"):]
            try:
                ckpt = pd.read_csv(metric_path)
                if metric not in ckpt.columns:
                    logger.warning(f"  {metric_path.name}: metric column missing, skipping")
                    continue
                seg_ids_unique = (
                    "segment_id" in ckpt.columns
                    and ckpt["segment_id"].nunique() == len(ckpt)
                )
                if seg_ids_unique:
                    # Unique segment_ids — safe to merge without row explosion.
                    merged = full_scores_df.merge(
                        ckpt[["segment_id", metric]], on="segment_id", how="left"
                    )
                    full_scores_df[metric] = merged[metric].values
                elif len(ckpt) == len(full_scores_df):
                    # Non-unique segment_ids (e.g. WMT DA domain keys shared across
                    # many rows): fall back to positional alignment. Row counts must
                    # match exactly — if they differ, those rows get NaN.
                    full_scores_df[metric] = ckpt[metric].values
                else:
                    # Row count mismatch with non-unique segment_ids (e.g. checkpoint
                    # was written before he/tier2 rows were added). Accept NaN for
                    # newly added rows; fill existing rows positionally.
                    n = min(len(ckpt), len(full_scores_df))
                    full_scores_df[metric] = float("nan")
                    full_scores_df.iloc[:n, full_scores_df.columns.get_loc(metric)] = (
                        ckpt[metric].values[:n]
                    )
                    logger.warning(
                        f"  {metric_path.name}: positional partial fill "
                        f"({len(ckpt)} ckpt rows vs {len(full_scores_df)} current) — "
                        f"new rows will have NaN for {metric}"
                    )
                metric_columns.append(metric)
                logger.info(f"  Loaded {metric} ({full_scores_df[metric].notna().sum()} non-null)")
            except Exception as exc:
                logger.warning(f"  Could not load {metric_path.name}: {exc}")
        if not metric_columns:
            raise RuntimeError(f"--analysis-only found no per-metric checkpoint files in {output_dir}")

        # Compute ensemble in analysis-only mode (normally done inside _run_metrics)
        neural = [c for c in ["comet", "xcomet", "cometkiwi", "cometkiwi23", "metricx"]
                  if c in full_scores_df.columns and not full_scores_df[c].isna().all()]
        if len(neural) >= 2:
            norm = full_scores_df[neural].copy()
            for col in neural:
                col_min, col_max = norm[col].min(), norm[col].max()
                if col_max > col_min:
                    norm[col] = (norm[col] - col_min) / (col_max - col_min)
            full_scores_df["ensemble"] = norm.mean(axis=1)
            metric_columns = metric_columns + ["ensemble"]
            logger.info(f"  Ensemble computed from: {neural}")
    else:
        logger.info("=== Running Metrics ===")
        metric_columns = _run_metrics(
            full_scores_df, settings,
            checkpoint_dir=output_dir,
            only_metrics=only_metrics,
        )
        if only_metrics:
            logger.info(f"Single-metric job complete ({only_metrics}). Skipping analysis.")
            return None

    logger.info("=== Correlation Analysis ===")
    resource_tiers = {k: list(v) for k, v in settings.languages.resource_tiers.items()}
    corr_df = run_correlation_analysis(full_scores_df, metric_columns,
                                       resource_tiers=resource_tiers)

    # Exclude GEMBA metric scores on Tier 2 (synthetic_mqm) data: the same model
    # (Llama-3.1-8B-Instruct) generates both the synthetic annotations and the GEMBA
    # metric scores, creating circular evaluation. GEMBA correlations are valid for
    # Tier 1a/1b only.
    if "gemba" in metric_columns:
        corr_df = corr_df[~(
            (corr_df["metric"] == "gemba") &
            (corr_df["annotation_tier"] == AnnotationTier.SYNTHETIC_MQM)
        )].copy()
        logger.info("GEMBA correlations on synthetic_mqm tier excluded (circular evaluation).")

    tier_summary = summarize_by_tier(corr_df)

    # Category breakdown: use raw WMT MQM span annotations if available
    # (google/wmt-mqm-human-evaluation TSVs, loaded separately from the HF dataset).
    # Falls back gracefully to empty if span data is not present.
    cat_corr_df = pd.DataFrame()
    span_dir = Path(getattr(settings.data, "wmt_mqm_span_dir", ""))
    if span_dir and span_dir.exists():
        try:
            from mqmbench.analysis.correlation import run_category_correlation
            logger.info("=== Category Correlation (Accuracy vs. Fluency) ===")
            span_df = load_wmt_mqm_spans(span_dir, lang_pairs=list(settings.data.wmt_mqm_pairs))
            if not span_df.empty:
                # Attach metric scores to span rows via segment_id lookup
                metric_lookup = (
                    full_scores_df[["segment_id"] + [c for c in metric_columns if c in full_scores_df.columns]]
                    .drop_duplicates("segment_id")
                )
                span_df = span_df.merge(metric_lookup, on="segment_id", how="left")
                cat_corr_df = run_category_correlation(
                    span_df, annotations_to_sentence_scores, metric_columns
                )
                logger.info(f"  Category correlations: {len(cat_corr_df)} rows")
        except Exception as exc:
            logger.warning(f"Category correlation skipped: {exc}")

    script_summary = summarize_by_script(corr_df)
    family_summary = summarize_by_family(corr_df)

    logger.info("=== Williams Tests ===")
    # Compare each metric against COMET (best-performing reference) per language.
    # Use the reference metric that's actually in the results; fall back to first available.
    reference_metric = next(
        (m for m in ["comet", "xcomet", "cometkiwi"] if m in metric_columns),
        metric_columns[0] if metric_columns else None,
    )
    williams_df = pd.DataFrame()
    if reference_metric and len(metric_columns) > 1:
        williams_df = run_williams_tests(
            full_scores_df, metric_columns,
            reference_metric=reference_metric,
        )
        logger.info(f"  Williams tests complete ({len(williams_df)} comparisons)")

    logger.info("=== Error Analysis ===")
    disagreement_df = analyze_metric_disagreements(
        full_scores_df, metric_columns, top_n=50,
    )
    logger.info(f"  Disagreement analysis: {len(disagreement_df)} rows")

    logger.info("=== COMET-Kiwi vs. COMET Comparison ===")
    kiwi_df = kiwi_vs_comet_by_tier(corr_df)
    if not kiwi_df.empty:
        logger.info(f"  Kiwi vs. COMET: {len(kiwi_df)} languages compared")
    else:
        logger.info("  Skipped (cometkiwi not in results — add to metrics.run)")

    logger.info("=== Medium > High Anomaly Analysis ===")
    anomaly_df = analyze_tier_anomaly(full_scores_df, metric_columns,
                                      resource_tiers=resource_tiers)
    if not anomaly_df.empty:
        logger.info(f"  Anomaly analysis: {len(anomaly_df)} lang×metric×year rows")
    else:
        logger.info("  Skipped (no 'year' column in scores — check wmt_mqm loader)")

    logger.info("=== Domain-stratified Analysis ===")
    domain_df = run_domain_analysis(full_scores_df, metric_columns,
                                    resource_tiers=resource_tiers)
    if not domain_df.empty:
        logger.info(f"  Domain analysis: {len(domain_df)} (lang×domain×metric) rows, "
                    f"domains: {sorted(domain_df['domain'].unique())}")
    else:
        logger.info("  Skipped (no 'domain' column in scores)")

    logger.info("=== System-level Analysis ===")
    sys_corr_df = run_system_level_analysis(full_scores_df, metric_columns,
                                            resource_tiers=resource_tiers)
    if not sys_corr_df.empty:
        logger.info(f"  System-level analysis: {len(sys_corr_df)} (lang×metric) rows")
    else:
        logger.info("  Skipped (no 'system' column in scores)")

    logger.info("=== Inter-metric Correlation Matrix ===")
    metric_corr_matrix = compute_metric_correlations(full_scores_df, metric_columns)
    if not metric_corr_matrix.empty:
        logger.info(f"  Metric correlation matrix: {metric_corr_matrix.shape}")

    logger.info("=== Reference Quality Effect ===")
    ref_quality_df = reference_quality_effect(full_scores_df, metric_columns,
                                              resource_tiers=resource_tiers)
    if not ref_quality_df.empty:
        logger.info(f"  Reference quality effect: {len(ref_quality_df)} rows")
    else:
        logger.info("  Skipped (missing COMET or Kiwi columns)")

    logger.info("=== Translation Direction Analysis ===")
    direction_df = run_direction_analysis(full_scores_df, metric_columns,
                                          resource_tiers=resource_tiers)
    if not direction_df.empty:
        direction_df.to_csv(output_dir / "direction_analysis.csv", index=False)
        logger.info(f"  Direction analysis: {len(direction_df)} rows → direction_analysis.csv")

    logger.info("=== Domain-Controlled Comparison (Ukrainian decomposition) ===")
    domain_ctrl_df = run_domain_controlled_comparison(
        full_scores_df, metric_columns, resource_tiers=resource_tiers,
    )
    if not domain_ctrl_df.empty:
        domain_ctrl_df.to_csv(output_dir / "domain_controlled_comparison.csv", index=False)
        logger.info(f"  Domain comparison: {len(domain_ctrl_df)} rows → domain_controlled_comparison.csv")

    logger.info("=== Morphological Type Analysis ===")
    morph_df = run_morphology_analysis(corr_df)
    if not morph_df.empty:
        logger.info(f"  Morphology analysis: {len(morph_df)} rows")

    logger.info("=== Direction × Morphology Interaction ===")
    dir_morph_df = run_direction_morphology_interaction(
        full_scores_df, metric_columns, resource_tiers=resource_tiers,
    )
    if not dir_morph_df.empty:
        dir_morph_df.to_csv(output_dir / "direction_morphology_interaction.csv", index=False)
        logger.info(f"  Interaction analysis: {len(dir_morph_df)} rows → direction_morphology_interaction.csv")

    logger.info("=== Sentence Length Analysis ===")
    length_df = run_length_analysis(full_scores_df, metric_columns,
                                    resource_tiers=resource_tiers)
    if not length_df.empty:
        logger.info(f"  Length analysis: {len(length_df)} rows")
    else:
        logger.info("  Skipped (no 'source' column in scores)")

    logger.info("=== Inter-rater Agreement Analysis ===")
    agreement_df = pd.DataFrame()
    if not cat_corr_df.empty:
        span_dir = Path(getattr(settings.data, "wmt_mqm_span_dir", ""))
        if span_dir and span_dir.exists():
            try:
                span_df_raw = load_wmt_mqm_spans(span_dir,
                                                  lang_pairs=list(settings.data.wmt_mqm_pairs))
                if not span_df_raw.empty:
                    metric_cols_avail = [c for c in metric_columns if c in full_scores_df.columns]
                    seg_lookup = (full_scores_df[["segment_id", "quality_score"] + metric_cols_avail]
                                  .drop_duplicates("segment_id"))
                    span_with_metrics = span_df_raw.merge(seg_lookup, on="segment_id", how="left")
                    agreement_df = run_rater_agreement_analysis(
                        span_with_metrics, full_scores_df, metric_columns)
                    if not agreement_df.empty:
                        logger.info(f"  Rater agreement: {len(agreement_df)} (lang×bin×metric) rows")
            except Exception as exc:
                logger.warning(f"  Rater agreement analysis skipped: {exc}")

    corr_df.to_csv(output_dir / "correlations.csv", index=False)
    tier_summary.to_csv(output_dir / "tier_summary.csv", index=False)
    script_summary.to_csv(output_dir / "script_type_summary.csv", index=False)
    family_summary.to_csv(output_dir / "family_summary.csv", index=False)
    if not cat_corr_df.empty:
        cat_corr_df.to_csv(output_dir / "category_correlations.csv", index=False)
    if not williams_df.empty:
        williams_df.to_csv(output_dir / "williams_tests.csv", index=False)
    if not disagreement_df.empty:
        disagreement_df.to_csv(output_dir / "metric_disagreements.csv", index=False)
    if not kiwi_df.empty:
        kiwi_df.to_csv(output_dir / "kiwi_vs_comet.csv", index=False)
    if not anomaly_df.empty:
        anomaly_df.to_csv(output_dir / "tier_anomaly.csv", index=False)
    if not domain_df.empty:
        domain_df.to_csv(output_dir / "domain_analysis.csv", index=False)
    if not sys_corr_df.empty:
        sys_corr_df.to_csv(output_dir / "system_level_correlations.csv", index=False)
    if not metric_corr_matrix.empty:
        metric_corr_matrix.to_csv(output_dir / "metric_correlation_matrix.csv")
    if not ref_quality_df.empty:
        ref_quality_df.to_csv(output_dir / "reference_quality_effect.csv", index=False)
    if not direction_df.empty:
        direction_df.to_csv(output_dir / "direction_analysis.csv", index=False)
    if not morph_df.empty:
        morph_df.to_csv(output_dir / "morphology_analysis.csv", index=False)
    if not length_df.empty:
        length_df.to_csv(output_dir / "length_analysis.csv", index=False)
    if not agreement_df.empty:
        agreement_df.to_csv(output_dir / "rater_agreement_analysis.csv", index=False)

    logger.info("=== Generating Plots ===")
    plot_correlation_by_resource_level(corr_df, plots_dir / "correlation_by_tier.png")
    plot_correlation_by_script_type(corr_df, plots_dir / "correlation_by_script.png")
    plot_correlation_by_language_family(corr_df, plots_dir / "correlation_by_family.png")
    if not cat_corr_df.empty:
        plot_metric_category_heatmap(cat_corr_df, plots_dir / "category_heatmap.png")
    plot_nontranslation_detection(full_scores_df, plots_dir / "nontranslation_detection.png")
    if not kiwi_df.empty:
        plot_kiwi_vs_comet_by_tier(kiwi_df, plots_dir / "kiwi_vs_comet.png")
    if not anomaly_df.empty:
        plot_tier_anomaly(anomaly_df, plots_dir / "tier_anomaly.png")
    if not domain_df.empty:
        plot_domain_analysis(domain_df, plots_dir / "domain_analysis.png")
    plot_score_distributions(full_scores_df, metric_columns,
                             resource_tiers=resource_tiers,
                             out_path=plots_dir / "score_distributions.png")
    if not metric_corr_matrix.empty:
        plot_metric_correlation_matrix(metric_corr_matrix,
                                       plots_dir / "metric_correlation_matrix.png")
    if not sys_corr_df.empty:
        plot_system_vs_segment_correlation(corr_df, sys_corr_df,
                                           plots_dir / "system_vs_segment.png")
    if not ref_quality_df.empty:
        plot_reference_quality_effect(ref_quality_df,
                                      plots_dir / "reference_quality_effect.png")
    if not direction_df.empty:
        plot_direction_analysis(direction_df, plots_dir / "direction_analysis.png")
    if not morph_df.empty:
        plot_morphology_analysis(morph_df, plots_dir / "morphology_analysis.png")
    if not length_df.empty:
        plot_length_analysis(length_df, plots_dir / "length_analysis.png")
    if not agreement_df.empty:
        plot_rater_agreement_analysis(agreement_df, plots_dir / "rater_agreement.png")

    logger.info(f"Pipeline complete. Results saved to {output_dir}/")
    return {
        "correlations": corr_df,
        "tier_summary": tier_summary,
        "script_type_summary": script_summary,
        "family_summary": family_summary,
        "category_correlations": cat_corr_df,
        "williams_tests": williams_df,
        "metric_disagreements": disagreement_df,
        "kiwi_vs_comet": kiwi_df,
        "tier_anomaly": anomaly_df,
        "domain_analysis": domain_df,
        "system_level_correlations": sys_corr_df,
        "metric_correlation_matrix": metric_corr_matrix,
        "reference_quality_effect": ref_quality_df,
    }


def _run_metrics(
    scores_df: pd.DataFrame,
    cfg,
    checkpoint_dir: Path | None = None,
    only_metrics: Optional[list[str]] = None,
) -> list[str]:
    """Run each configured metric and add score columns to scores_df in place.

    If checkpoint_dir is provided:
    - Saves a checkpoint CSV after each metric completes.
    - On startup, reads any existing checkpoint and merges already-computed
      columns back into scores_df so those metrics are skipped this run.
      This lets a failed job resume from where it left off.
    """
    # only_metrics overrides the full run list (used for single-metric SLURM jobs)
    metrics_to_run = list(only_metrics) if only_metrics else list(cfg.metrics.run)
    added_columns = []

    # Resume from per-metric checkpoint files. Each metric writes its own
    # scores_{metric}.csv so parallel jobs never share a file.
    if checkpoint_dir is not None:
        skipped, recomputing = [], []
        for metric in list(metrics_to_run):
            metric_path = checkpoint_dir / f"scores_{metric}.csv"
            if metric_path.exists():
                try:
                    ckpt = pd.read_csv(metric_path)
                    if metric in ckpt.columns and len(ckpt) == len(scores_df):
                        if ckpt[metric].notna().all():
                            scores_df[metric] = ckpt[metric].values
                            added_columns.append(metric)
                            metrics_to_run.remove(metric)
                            skipped.append(metric)
                        else:
                            missing_n = int(ckpt[metric].isna().sum())
                            recomputing.append(f"{metric}({missing_n} missing)")
                    else:
                        recomputing.append(metric)
                except Exception as exc:
                    logger.warning(f"Could not load checkpoint for {metric} ({exc}) — recomputing")
        if skipped:
            logger.info(f"Resuming from checkpoint — skipping: {skipped}")
        if recomputing:
            logger.info(f"Checkpoint incomplete for: {recomputing} — will recompute")

    def _checkpoint(name: str) -> None:
        if checkpoint_dir is not None:
            path = checkpoint_dir / f"scores_{name}.csv"
            id_cols = [c for c in ("segment_id", "lang", "annotation_tier") if c in scores_df.columns]
            scores_df[id_cols + [name]].to_csv(path, index=False)
            logger.info(f"Checkpoint saved after {name}: {path}")

    if "bleu" in metrics_to_run:
        logger.info("Computing BLEU...")
        from mqmbench.metrics import bleu
        sources, hyps, refs = _text_lists(scores_df)
        scores_df["bleu"] = bleu.score(sources, hyps, refs)
        added_columns.append("bleu")
        _checkpoint("bleu")

    if "chrf" in metrics_to_run:
        logger.info("Computing ChrF++...")
        from mqmbench.metrics import chrf
        sources, hyps, refs = _text_lists(scores_df)
        scores_df["chrf"] = chrf.score(sources, hyps, refs)
        added_columns.append("chrf")
        _checkpoint("chrf")

    if "bertscore" in metrics_to_run:
        logger.info("Computing BERTScore...")
        from mqmbench.metrics import bertscore
        sources, hyps, refs = _text_lists(scores_df)
        scores_df["bertscore"] = bertscore.score(
            sources, hyps, refs,
            model_type=cfg.metrics.bertscore.model,
            batch_size=cfg.metrics.bertscore.batch_size,
        )
        added_columns.append("bertscore")
        _checkpoint("bertscore")

    if "comet" in metrics_to_run:
        logger.info("Computing COMET...")
        from mqmbench.metrics import comet
        sources, hyps, refs = _text_lists(scores_df)
        scores_df["comet"] = comet.score(
            sources, hyps, refs,
            model_name=cfg.metrics.comet.model,
            batch_size=cfg.metrics.comet.batch_size,
            gpus=cfg.metrics.comet.gpus,
        )
        added_columns.append("comet")
        _checkpoint("comet")

    if "xcomet" in metrics_to_run:
        logger.info("Computing xCOMET...")
        from mqmbench.metrics import comet
        sources, hyps, refs = _text_lists(scores_df)
        xcomet_cache = str(checkpoint_dir / "xcomet_cache.jsonl") if checkpoint_dir else None
        scores_df["xcomet"] = comet.score_xcomet(
            sources, hyps, refs,
            model_name=cfg.metrics.xcomet.model,
            batch_size=cfg.metrics.xcomet.batch_size,
            gpus=cfg.metrics.xcomet.gpus,
            cache_file=xcomet_cache,
        )
        added_columns.append("xcomet")
        _checkpoint("xcomet")
        gc.collect()

    if "xcometxxl" in metrics_to_run:
        logger.info("Computing xCOMET-XXL...")
        from mqmbench.metrics import comet
        sources, hyps, refs = _text_lists(scores_df)
        scores_df["xcometxxl"] = comet.score_xcomet(
            sources, hyps, refs,
            model_name=cfg.metrics.xcometxxl.model,
            batch_size=cfg.metrics.xcometxxl.batch_size,
            gpus=cfg.metrics.xcometxxl.gpus,
        )
        added_columns.append("xcometxxl")
        _checkpoint("xcometxxl")
        gc.collect()

    if "bleurt" in metrics_to_run:
        logger.info("Computing BLEURT...")
        from mqmbench.metrics import bleurt as bleurt_metric
        sources, hyps, refs = _text_lists(scores_df)
        scores_df["bleurt"] = bleurt_metric.score(
            hyps, refs,
            model_name=cfg.metrics.bleurt.model,
            batch_size=cfg.metrics.bleurt.batch_size,
        )
        added_columns.append("bleurt")
        _checkpoint("bleurt")
        gc.collect()

    if "cometkiwi" in metrics_to_run:
        logger.info("Computing COMET-Kiwi 2022 (reference-free)...")
        from mqmbench.metrics import comet
        sources, hyps, _ = _text_lists(scores_df)
        scores_df["cometkiwi"] = comet.score_kiwi(
            sources, hyps,
            model_name=cfg.metrics.cometkiwi.model,
            batch_size=cfg.metrics.cometkiwi.batch_size,
            gpus=cfg.metrics.cometkiwi.gpus,
        )
        added_columns.append("cometkiwi")
        _checkpoint("cometkiwi")
        gc.collect()

    if "cometkiwi23" in metrics_to_run:
        logger.info("Computing COMET-Kiwi 2023 XL (reference-free)...")
        from mqmbench.metrics import comet
        sources, hyps, _ = _text_lists(scores_df)
        scores_df["cometkiwi23"] = comet.score_kiwi(
            sources, hyps,
            model_name=cfg.metrics.cometkiwi23.model,
            batch_size=cfg.metrics.cometkiwi23.batch_size,
            gpus=cfg.metrics.cometkiwi23.gpus,
        )
        added_columns.append("cometkiwi23")
        _checkpoint("cometkiwi23")
        gc.collect()

    if "metricx" in metrics_to_run:
        logger.info("Computing MetricX-24 (Google WMT24 winner)...")
        from mqmbench.metrics import metricx as metricx_metric
        sources, hyps, refs = _text_lists(scores_df)
        scores_df["metricx"] = metricx_metric.score(
            sources, hyps, refs,
            model_name=cfg.metrics.metricx.model,
            batch_size=cfg.metrics.metricx.batch_size,
        )
        added_columns.append("metricx")
        _checkpoint("metricx")
        gc.collect()

    # GEMBA is gated by run_gemba (separate from metrics.run) AND by only_metrics:
    # if only_metrics is specified (single-metric job), skip GEMBA unless
    # explicitly requested with --only-metrics gemba.
    _run_gemba = (
        getattr(cfg.metrics, "run_gemba", False)
        and (only_metrics is None or "gemba" in only_metrics)
    )
    if _run_gemba:
        # GEMBA is an LLM inference metric — running it on 700k+ segments with a
        # local Llama model would take 30–100 hours. Restrict to MQM tier only
        # (~85k segments), which is also where it makes most analytical sense
        # (professional human judgments vs. LLM-as-judge comparison).
        #
        # Force-free GPU memory from neural metrics before loading the LLM.
        gc.collect()
        try:
            import torch as _torch
            if _torch.cuda.is_available():
                _torch.cuda.empty_cache()
        except Exception:
            pass

        gemba_df = scores_df[scores_df["annotation_tier"] == "human_mqm"].copy()
        logger.info(f"Computing GEMBA-MQM on MQM tier only ({len(gemba_df)} segments)...")
        from mqmbench.metrics import gemba
        g_src, g_hyp, g_ref = _text_lists(gemba_df)
        gemba_cache = str(checkpoint_dir / "gemba_cache.jsonl") if checkpoint_dir else None
        _gcfg = getattr(cfg.metrics, "gemba", None)
        raw_penalties = gemba.score(g_src, g_hyp, g_ref,
                                    model_name=cfg.metrics.gemba_model,
                                    batch_size=getattr(_gcfg, "batch_size", 32),
                                    max_new_tokens=getattr(_gcfg, "max_new_tokens", 32),
                                    cache_file=gemba_cache)
        scores_df["gemba"] = float("nan")
        scores_df.loc[gemba_df.index, "gemba"] = [1.0 / (1.0 + p) for p in raw_penalties]
        added_columns.append("gemba")
        _checkpoint("gemba")

    # Ensemble: average of available neural metrics (no GPU cost).
    # MetricX scores are in [0,25] (higher=better after our flip), while COMET
    # scores are in [0,1]. Normalize each to [0,1] before averaging so no single
    # metric dominates by scale.
    neural = [c for c in ["comet", "xcomet", "cometkiwi", "cometkiwi23", "metricx"]
              if c in scores_df.columns]
    if len(neural) >= 2:
        norm = scores_df[neural].copy()
        for col in neural:
            col_min, col_max = norm[col].min(), norm[col].max()
            if col_max > col_min:
                norm[col] = (norm[col] - col_min) / (col_max - col_min)
        scores_df["ensemble"] = norm.mean(axis=1)
        added_columns.append("ensemble")
        logger.info(f"Ensemble metric computed from: {neural}")

    return added_columns


def _text_lists(df: pd.DataFrame) -> tuple[list, list, list]:
    """Extract source/hypothesis/reference as plain string lists (NaN → empty string)."""
    def _to_str(col):
        return df[col].fillna("").astype(str).tolist()
    return _to_str("source"), _to_str("hypothesis"), _to_str("reference")
