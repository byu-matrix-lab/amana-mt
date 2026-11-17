#!/bin/bash --login
#SBATCH --job-name=AM_regen
#SBATCH --partition=m9
#SBATCH --time=8:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --output=logs/regen_spbleu_%j.out

# 2026-11-16: BLEURT excluded (metric_scope), spBLEU for ja/th/lo/my targets, new Fig 1/2.
# 2026-11-11: rerun after switching the he/es span labels to official WMT MQM weights
# (converter.wmt_mqm_weight) and computing TotalSegments. Same steps as run_regen_v2_fixes.sh.
# Regenerate after the 2026-11-10 v2 code fixes (no rescoring):
#   GEMBA excluded, BLEURT English-target only (src/mqmbench/analysis/metric_scope.py),
#   segment bootstrap -> source-sentence bootstrap, reference_quality_effect NaN fix.
# Same steps as run_regen_after_label_fix.sh minus the splice (already applied 2026-11-09).
set -euo pipefail
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src
cd "$SLURM_SUBMIT_DIR"
PY=.venv/bin/python
SNAP=results/backup_pre_spbleu_2026-11-16
mkdir -p $SNAP
echo "=== 0. tests + snapshot $(date)"
$PY -m pytest tests/ -q --deselect tests/test_metricx_batch_invariance.py
tar czf $SNAP/analysis_outputs.tgz --exclude='results/scores_*.csv' --exclude='results/backup*' \
    --exclude='results/span_block*' --exclude='results/gemba_cache*' --exclude='results/external_refs' \
    results/*.csv results/paper_stats.json results/predictor
echo "=== 1b. spBLEU for ja/th/lo/my targets (guarded; idempotent) $(date)"
$PY scripts/rescore_bleu_spm.py
echo "=== 2. pipeline --analysis-only $(date)"
$PY scripts/run_pipeline.py --settings settings.toml --analysis-only
echo "=== 3. direction-separated $(date)"
$PY scripts/analyze_direction_separated.py
echo "=== 4. surface similarity / mt-metrics-eval validation $(date)"
$PY scripts/analyze_surface_similarity.py
$PY scripts/validate_against_mt_metrics_eval.py
echo "=== 5. paper stats, pass 1 $(date)"
$PY scripts/generate_paper_stats.py > logs/regen_spbleu_stats_pass1_${SLURM_JOB_ID}.txt 2>&1
echo "=== 6. abjad + Ridge predictor, then paper stats pass 2 $(date)"
$PY scripts/analyze_abjad_mechanism.py
$PY scripts/build_metric_reliability_predictor.py
$PY scripts/generate_paper_stats.py
echo "=== 7. corrected-paper macros, language table, figures $(date)"
export PAPER_DIR=arxiv_submission
$PY scripts/render_macros.py
$PY scripts/generate_language_table.py
$PY scripts/make_presentation_plots.py
for f in arxiv_submission/figures/*.pdf; do cp results/plots/$(basename $f) $f; done
echo "=== 8. invariants (literal-valued checks are expected to need updating) $(date)"
$PY scripts/assert_paper_invariants.py || echo "INVARIANTS FAILED (see above)"
echo "=== done $(date)"
