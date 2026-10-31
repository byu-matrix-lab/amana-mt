#!/bin/bash
#SBATCH --job-name=mqm_control
#SBATCH --partition=m9
#SBATCH --time=00:30:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=2
#SBATCH --output=logs/mqm_control_%j.out
cd /home/it238/projects/multilingual-mqm-benchmark/multilingual-mqm-benchmark
python3 scripts/audit/mqm_control.py ~/nobackup/archive/mtme/mt-metrics-eval-v2
