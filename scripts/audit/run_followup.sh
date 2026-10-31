#!/bin/bash
#SBATCH --job-name=followup
#SBATCH --partition=m9
#SBATCH --time=03:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/followup_%j.out
cd /home/it238/projects/multilingual-mqm-benchmark/multilingual-mqm-benchmark
M=~/nobackup/archive/mtme/mt-metrics-eval-v2
python3 scripts/audit/mqm_control.py $M > logs/mqm_control_refactor_check.out 2>&1
python3 scripts/audit/followup_analyses.py $M
