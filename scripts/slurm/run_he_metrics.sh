#!/bin/bash --login

#SBATCH --job-name=mqmbench_he
#SBATCH --partition=cs
#SBATCH --qos=cs
#SBATCH --time=06:00:00
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=256G
#SBATCH --gres=gpu:1
#SBATCH --output=logs/mqmbench_he_%j.out

# Compute all metrics for the he-en language pair (he is missing from the HF
# dataset but the TSV spans are in ../wmt-mqm-human-evaluation).
# Appends he rows to the existing per-metric score CSVs so that --analysis-only
# can pick them up via segment_id merge without re-running all other languages.

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=$SLURM_CPUS_ON_NODE

cd "$SLURM_SUBMIT_DIR"

nvidia-smi || echo "nvidia-smi not available"

srun .venv/bin/python scripts/compute_he_scores.py --settings settings.toml
