#!/bin/bash --login

#SBATCH --job-name=mqmbench_es_fix
#SBATCH --partition=cs
#SBATCH --qos=cs
#SBATCH --time=06:00:00
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=256G
#SBATCH --gres=gpu:1
#SBATCH --output=logs/mqmbench_es_fix_%j.out

# Spanish (en-es) checkpoint rows were removed after discovering the same
# segment_id-scheme mismatch that hit Hebrew (advisor review, 2026-09-11).
# Regenerate with the now-fixed, consistent segment_id disambiguation.

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=$SLURM_CPUS_ON_NODE

cd "$SLURM_SUBMIT_DIR"

nvidia-smi || echo "nvidia-smi not available"

srun .venv/bin/python scripts/compute_span_scores.py --settings settings.toml --langs es
