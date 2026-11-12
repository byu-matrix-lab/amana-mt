#!/bin/bash --login
#SBATCH --job-name=regen_labelfix_r5
#SBATCH --partition=m9
#SBATCH --time=3:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --output=logs/regen_labelfix_r5_%j.out

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
# Resume of run_regen_after_label_fix.sh from step 5 (job 15187975 died there on
# a missing predictor n_units key; steps 0-4 completed in that job).
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
