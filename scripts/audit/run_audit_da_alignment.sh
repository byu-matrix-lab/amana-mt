#!/bin/bash --login
#SBATCH --job-name=audit_da_align
#SBATCH --partition=m9
#SBATCH --time=01:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --output=logs/audit_da_align_%j.out
cd "$SLURM_SUBMIT_DIR"
export HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1
.venv/bin/python3 scripts/audit/audit_da_alignment.py
