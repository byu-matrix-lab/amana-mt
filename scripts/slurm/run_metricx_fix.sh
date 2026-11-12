#!/bin/bash --login
#SBATCH --job-name=metricx_fix
#SBATCH --partition=dwmatrix
#SBATCH --qos=matrix
#SBATCH --time=30:00:00
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=192G
#SBATCH --gres=gpu:1
#SBATCH --output=logs/metricx_fix_%j.out

# MetricX-24 EOS/padding fix (2026-11-05): regression test, then full rescore.
# Main benchmark rescore writes to results_metricx_fix/ (NOT results/). A chrF
# column is recomputed alongside it so row alignment can be verified before the
# new MetricX column replaces results/scores_metricx.csv.
# de-en / en-zh: their scripts recompute only a missing metricx column
# (originals backed up in results/backup_pre_metricx_fix_2026-11-05/).
#
# Submit from project root:  sbatch scripts/slurm/run_metricx_fix.sh
set -euo pipefail
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
cd "$SLURM_SUBMIT_DIR"
nvidia-smi || true

echo "=== 1. regression test (fixed code) $(date)"
.venv/bin/python -m pytest tests/test_metricx_batch_invariance.py -q -rs -p no:cacheprovider | tee logs/metricx_fix_pytest_${SLURM_JOB_ID}.txt
if grep -qi skipped logs/metricx_fix_pytest_${SLURM_JOB_ID}.txt; then echo 'regression test SKIPPED (model not loaded) -> abort'; exit 1; fi

echo "=== 1b. same check against the old (buggy) implementation, expected to differ"
.venv/bin/python - <<'PY'
import importlib.util, sys
sys.path.insert(0, "src")
spec = importlib.util.spec_from_file_location("old_mx", "logs/metricx_buggy_reference.py")
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
from mqmbench.metrics import metricx as new
s = ("Das Haus ist klein.", "The house is small.", "The house is small.")
l = ("Die Regierung kündigte am Montag ein umfassendes Paket von Maßnahmen an, das die Inflation bremsen soll.",
     "On Monday the government announced a comprehensive package of measures to curb inflation.",
     "On Monday, the government unveiled a broad set of measures meant to slow inflation.")
for name, m in [("old", old), ("new", new)]:
    a = m.score([s[0]], [s[1]], [s[2]], batch_size=1)[0]
    b = m.score([s[0], l[0]], [s[1], l[1]], [s[2], l[2]], batch_size=2)[0]
    print(f"{name}: alone={a:.3f} batched={b:.3f} diff={a-b:+.3f}")
PY

echo "=== 2. main benchmark rescore (chrf + metricx) -> results_metricx_fix/ $(date)"
.venv/bin/python scripts/run_pipeline.py --settings settings_metricx_fix.toml --only-metrics chrf metricx \
  || echo "pipeline exited nonzero (analysis may fail with only 2 metrics; checkpoints are written first)"
ls -la results_metricx_fix/scores_chrf.csv results_metricx_fix/scores_metricx.csv

echo "=== 3. de-en / en-zh metricx columns $(date)"
.venv/bin/python - <<'PY'
import pandas as pd
for f in ["results/scores_de_en.csv", "results/scores_en_zh.csv"]:
    d = pd.read_csv(f)
    d.drop(columns=["metricx"]).to_csv(f, index=False)
    print("dropped metricx from", f)
PY
.venv/bin/python scripts/score_de_en.py
.venv/bin/python scripts/score_en_zh.py
echo "=== done $(date)"
