#!/bin/bash --login
#SBATCH --job-name=audit_vs_official
#SBATCH --partition=m9
#SBATCH --time=01:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=48G
#SBATCH --output=logs/audit_vs_official_%j.out
cd "$SLURM_SUBMIT_DIR"
export HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1
.venv/bin/python3 scripts/audit/audit_da_vs_official.py $HOME/nobackup/archive/mtme/mt-metrics-eval-v2
