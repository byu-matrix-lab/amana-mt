#!/bin/bash
#SBATCH --job-name=score_de_en
#SBATCH --partition=dwmatrix
#SBATCH --qos=matrix
#SBATCH --time=04:00:00
#SBATCH --mem=80G
#SBATCH --gres=gpu:1
#SBATCH --output=logs/score_de_en_%j.out
#SBATCH --error=logs/score_de_en_%j.err

# Score de-en (German→English, n=134,796) — genuinely unseen X→en fusional pair.
# Lookup table predicts CK23 wins (consistent with cs-en and lt-en).
#
# MODELS SCORED:
#   - Unbabel/wmt22-comet-da       (COMET-22, reference-based)
#   - Unbabel/wmt23-cometkiwi-da-xl (CK23, reference-free)
#   - MetricX-24                   (reference-based, Google)
#
# Submit from project root:
#   mkdir -p logs
#   sbatch scripts/slurm/run_score_de_en.sh

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"
PROJECT_ROOT="$(pwd)"

echo "=== de-en scoring job start: $(date) ==="
echo "Node: $SLURMD_NODENAME"
echo "CUDA devices: $CUDA_VISIBLE_DEVICES"
echo "Working dir: $PROJECT_ROOT"

export HF_HUB_OFFLINE=1
export TOKENIZERS_PARALLELISM=false

mkdir -p logs

.venv/bin/python scripts/score_de_en.py \
    2>&1 | tee logs/score_de_en_run.log

echo "=== Job complete: $(date) ==="
echo "Output: results/scores_de_en.csv"
