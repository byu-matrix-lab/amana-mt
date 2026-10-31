#!/bin/bash
#SBATCH --job-name=score_en_zh
#SBATCH --partition=dwmatrix
#SBATCH --qos=matrix
#SBATCH --time=06:00:00
#SBATCH --mem=80G
#SBATCH --gres=gpu:1
#SBATCH --output=logs/score_en_zh_%j.out
#SBATCH --error=logs/score_en_zh_%j.err

# Score en-zh (English→Chinese WMT DA, ~110k rows): fills the en→X isolating cell (advisor feedback).
# Also computes chrF++, BLEU (13a, pipeline-consistent) and BLEU (zh tokenizer).
#
# MODELS SCORED:
#   - Unbabel/wmt22-comet-da       (COMET-22, reference-based)
#   - Unbabel/wmt23-cometkiwi-da-xl (CK23, reference-free)
#   - MetricX-24                   (reference-based, Google)
#
# Submit from project root:
#   mkdir -p logs
#   sbatch scripts/slurm/run_score_en_zh.sh

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"
PROJECT_ROOT="$(pwd)"

echo "=== en-zh scoring job start: $(date) ==="
echo "Node: $SLURMD_NODENAME"
echo "CUDA devices: $CUDA_VISIBLE_DEVICES"
echo "Working dir: $PROJECT_ROOT"

export HF_HUB_OFFLINE=1
export TOKENIZERS_PARALLELISM=false

mkdir -p logs

.venv/bin/python scripts/score_en_zh.py \
    2>&1 | tee logs/score_en_zh_run.log

echo "=== Job complete: $(date) ==="
echo "Output: results/scores_en_zh.csv, results/en_zh_correlations.csv"
