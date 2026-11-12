#!/bin/bash --login
#SBATCH --job-name=span_rescore
#SBATCH --partition=dwmatrix
#SBATCH --qos=matrix
#SBATCH --time=8:00:00
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=64G
#SBATCH --gres=gpu:1
#SBATCH --output=logs/span_rescore_%j.out

# Rebuild + rescore the he-en/en-es span block after the 2026-11-09 label fixes.
# Writes results/span_block_2026-11-09/; results/ itself is not modified
# (scripts/splice_span_block.py does that, after checks).
# Submit from project root:  sbatch scripts/slurm/run_rescore_span_block.sh
set -euo pipefail
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
cd "$SLURM_SUBMIT_DIR"
nvidia-smi || true
echo "=== tests $(date)"
PYTHONPATH=src .venv/bin/python -m pytest tests/test_label_fixes.py tests/test_converter.py -q -rs -p no:cacheprovider
echo "=== rescore span block $(date)"
.venv/bin/python scripts/rescore_span_block.py
echo "=== done $(date)"
