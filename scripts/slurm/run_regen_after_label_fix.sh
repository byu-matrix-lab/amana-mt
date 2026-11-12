#!/bin/bash --login
#SBATCH --job-name=regen_labelfix
#SBATCH --partition=m9
#SBATCH --time=8:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --output=logs/regen_labelfix_%j.out

# Regenerate every analysis CSV, paper_stats.json and the corrected paper's
# macros/figures after the 2026-11-09 label fixes + MetricX EOS fix.
# Run after scripts/slurm/run_rescore_span_block.sh succeeds:
#   sbatch --dependency=afterok:<rescore_jobid> scripts/slurm/run_regen_after_label_fix.sh
# Paper outputs go to arxiv_submission/ (PAPER_DIR); latex/ (published) is untouched.
set -euo pipefail
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src
cd "$SLURM_SUBMIT_DIR"
PY=.venv/bin/python
SNAP=results/backup_pre_label_fix_2026-11-09
mkdir -p $SNAP
echo "=== 0. snapshot analysis outputs $(date)"
tar czf $SNAP/analysis_outputs.tgz --exclude='results/scores_*.csv' --exclude='results/backup*' \
    --exclude='results/span_block*' --exclude='results/gemba_cache*' --exclude='results/external_refs' \
    results/*.csv results/paper_stats.json results/predictor
echo "=== 1. splice he/es block + MetricX fix into results/ $(date)"
$PY scripts/splice_span_block.py
echo "=== 2. pipeline --analysis-only $(date)"
$PY scripts/run_pipeline.py --settings settings.toml --analysis-only
echo "=== 3. direction-separated $(date)"
$PY scripts/analyze_direction_separated.py
echo "=== 4. surface similarity / mt-metrics-eval validation $(date)"
$PY scripts/analyze_surface_similarity.py
$PY scripts/validate_against_mt_metrics_eval.py
echo "=== 5. paper stats, pass 1 (writes corrected he/es rows into correlations.csv / direction_analysis.csv) $(date)"
$PY scripts/generate_paper_stats.py > logs/regen_labelfix_stats_pass1_${SLURM_JOB_ID}.txt
echo "=== 6. abjad + Ridge predictor (read those CSVs), then paper stats pass 2 $(date)"
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
