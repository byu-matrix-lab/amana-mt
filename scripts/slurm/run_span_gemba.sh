#!/bin/bash
#SBATCH --job-name=span_gemba
#SBATCH --output=logs/span_gemba_%j.out
#SBATCH --error=logs/span_gemba_%j.err
#SBATCH --partition=cs
#SBATCH --qos=cs
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --gres=gpu:1
#SBATCH --time=04:00:00
#SBATCH --nodelist=cs-1-3

set -euo pipefail

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_DATASETS_OFFLINE=1

cd "$SLURM_SUBMIT_DIR"

echo "=== span_gemba job $SLURM_JOB_ID started $(date) ==="
echo "Node: $SLURMD_NODENAME  GPU: $CUDA_VISIBLE_DEVICES"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || true

.venv/bin/python scripts/compute_span_gemba.py --settings settings.toml

echo "=== Done $(date) ==="
