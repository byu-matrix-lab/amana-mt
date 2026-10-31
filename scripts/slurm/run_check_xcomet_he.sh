#!/bin/bash --login

#SBATCH --job-name=mqmbench_xcomet_he_check
#SBATCH --partition=cs
#SBATCH --qos=cs
#SBATCH --time=01:00:00
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=128G
#SBATCH --gres=gpu:1
#SBATCH --output=logs/mqmbench_xcomet_he_check_%j.out

# Diagnostic: does scores_xcomet.csv's Hebrew checkpoint match a correct- or
# empty-reference recomputation? See check_xcomet_he_reference.py docstring.

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=$SLURM_CPUS_ON_NODE

cd "$SLURM_SUBMIT_DIR"

nvidia-smi || echo "nvidia-smi not available"

srun .venv/bin/python scripts/check_xcomet_he_reference.py
