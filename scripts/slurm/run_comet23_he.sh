#!/bin/bash --login
# Score Hebrew WMT23 segments with COMET-23 (wmt23-comet-da).
#
# Pre-requisite — run on login node before submitting:
#   .venv/bin/python -c "from comet import download_model; download_model('Unbabel/wmt23-comet-da')"
#
# Submit:
#   sbatch scripts/slurm/run_comet23_he.sh

#SBATCH --job-name=comet23_he
#SBATCH --partition=dwmatrix
#SBATCH --qos=matrix
#SBATCH --time=02:00:00
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=64G
#SBATCH --gres=gpu:1
#SBATCH --requeue
#SBATCH --signal=SIGHUP@90
#SBATCH --output=logs/comet23_he_%j.out

export OMP_NUM_THREADS=$SLURM_CPUS_ON_NODE
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

cd "$SLURM_SUBMIT_DIR"

nvidia-smi || echo "nvidia-smi not available"

echo "=== Scoring Hebrew with COMET-23 ==="
srun .venv/bin/python scripts/compute_comet23_he.py --settings settings.toml

echo "=== Running abjad mechanism analysis ==="
srun .venv/bin/python scripts/analyze_abjad_mechanism.py --settings settings.toml
