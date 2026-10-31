#!/bin/bash --login

#SBATCH --job-name=mqmbench_paperstats
#SBATCH --partition=cs
#SBATCH --qos=cs
#SBATCH --time=00:30:00
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=logs/mqmbench_paperstats_%j.out

# CPU-only, no GPU needed. Runs on a dedicated node instead of the shared
# login node, which is frequently oversubscribed (seen: 60 users, 1 usable
# core, load average 11+ -- a purely single-threaded, CPU-bound script like
# this one can take 10x longer there than on a dedicated allocation).

cd "$SLURM_SUBMIT_DIR"

.venv/bin/python3 scripts/generate_paper_stats.py
