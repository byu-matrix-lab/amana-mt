#!/bin/bash --login

#SBATCH --job-name=mqmbench_analysis
#SBATCH --partition=cs
#SBATCH --qos=cs
#SBATCH --time=02:00:00
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=512G
#SBATCH --output=logs/mqmbench_analysis_%j.out

# Re-run correlation analysis after he-en metrics and/or Tier 2 regeneration.
# No GPU needed — analysis only reads checkpoint CSVs and computes statistics.

export HF_HUB_OFFLINE=1

cd "$SLURM_SUBMIT_DIR"

.venv/bin/python scripts/run_pipeline.py --settings settings.toml --analysis-only
