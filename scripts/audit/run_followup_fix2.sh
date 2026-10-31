#!/bin/bash
#SBATCH --job-name=followup_fix2
#SBATCH --partition=m9
#SBATCH --time=02:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/followup_fix2_%j.out
cd /home/it238/projects/multilingual-mqm-benchmark/multilingual-mqm-benchmark
export HF_HUB_OFFLINE=1
python3 scripts/audit/diagnostic_validation.py
python3 scripts/audit/followup_analyses.py ~/nobackup/archive/mtme/mt-metrics-eval-v2 > logs/followup_final.out 2>&1
grep -A 20 "=== D." logs/followup_final.out
