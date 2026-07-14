#!/bin/bash
# Submit all metrics in PARALLEL on dwmatrix (8× A100, 2 TB RAM).
# Each metric runs in its own process on its own GPU — no MaxRSS accumulation,
# no sequential wait. Analysis job depends on all metrics completing.
#
# Wall clock: ~14h (GEMBA-limited) vs ~47h sequential.
# Usage: bash scripts/slurm/submit_chain.sh

set -e
cd "$(dirname "$0")/../.."

PARTITION=dwmatrix
QOS=matrix
VENV=.venv/bin/python
SCRIPT=scripts/run_pipeline.py
SETTINGS=settings.toml
LOG=logs

mkdir -p "$LOG"

submit() {
    local name=$1 time=$2 mem=$3 gpu_flag=$4 dep_flag=$5 metric=$6
    sbatch $dep_flag \
        --partition=$PARTITION --qos=$QOS \
        --time=$time --mem=$mem $gpu_flag \
        --ntasks=1 --nodes=1 \
        --job-name="mqm_${name}" \
        --output="${LOG}/mqm_${name}_%j.out" \
        --wrap="cd \$SLURM_SUBMIT_DIR && \
                export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 && \
                $VENV -u $SCRIPT --settings $SETTINGS --only-metrics ${metric}" \
        | awk '{print $NF}'
}

echo "Submitting parallel metrics on $PARTITION (8× A100)..."
# Memory notes (learned from empirical OOM testing):
# - All jobs need ≥128G even though data loading measures 2.37 GB on the login
#   node. Compute-node cgroup accounting adds ~60-100 GB overhead (CUDA context
#   + shared library pages) that doesn't appear in login-node profiling.
# - xcomet/cometkiwi23: 13 GB xlm-roberta-xl model + data → need 128G
# - gemba: Llama 8B (16 GB) + data → need 128G
# - bleurt/cometkiwi/metricx: smaller models but same data overhead → 128G

JOB_XCOMET=$(submit   xcomet      20:00:00 128G "--gres=gpu:1" "" xcomet)
echo "  xcomet:      $JOB_XCOMET  (GPU, 20h, 128G)"

JOB_KIWI23=$(submit   cometkiwi23 20:00:00 128G "--gres=gpu:1" "" cometkiwi23)
echo "  cometkiwi23: $JOB_KIWI23  (GPU, 20h, 128G)"

JOB_GEMBA=$(submit    gemba       20:00:00 128G "--gres=gpu:1" "" gemba)
echo "  gemba:       $JOB_GEMBA   (GPU, 20h, 128G — Llama, max_new_tokens=64)"

JOB_BLEURT=$(submit   bleurt      06:00:00 128G "--gres=gpu:1" "" bleurt)
echo "  bleurt:      $JOB_BLEURT  (GPU, 6h, 128G)"

JOB_KIWI22=$(submit   cometkiwi   06:00:00 128G "--gres=gpu:1" "" cometkiwi)
echo "  cometkiwi:   $JOB_KIWI22  (GPU, 6h, 128G)"

JOB_METRICX=$(submit  metricx     06:00:00 128G "--gres=gpu:1" "" metricx)
echo "  metricx:     $JOB_METRICX (GPU, 6h, 128G)"

# bleu/chrf don't need GPU but bertscore and comet do; bundle together
JOB_BLEU=$(submit bleu_etc 06:00:00 128G "--gres=gpu:1" "" "bleu chrf bertscore comet")
echo "  bleu_etc:    $JOB_BLEU    (GPU, 6h, 128G — bleu/chrf/bertscore/comet)"

# Analysis runs after ALL metrics complete
ALL_JOBS="${JOB_XCOMET}:${JOB_KIWI23}:${JOB_GEMBA}:${JOB_BLEURT}:${JOB_KIWI22}:${JOB_METRICX}:${JOB_BLEU}"
JOB_ANALYSIS=$(sbatch \
    --dependency=afterok:${ALL_JOBS} \
    --partition=$PARTITION --qos=$QOS \
    --time=01:00:00 --mem=32G \
    --ntasks=1 --nodes=1 \
    --job-name="mqm_analysis" \
    --output="${LOG}/mqm_analysis_%j.out" \
    --wrap="cd \$SLURM_SUBMIT_DIR && \
            export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 && \
            $VENV -u $SCRIPT --settings $SETTINGS --analysis-only" \
    | awk '{print $NF}')
echo "  analysis:    $JOB_ANALYSIS (afterok all, 1h)"

echo ""
echo "All 7 metrics running in parallel. Analysis starts when all complete."
echo "Expected wall clock: ~14h (GEMBA-limited at max_new_tokens=64)."
echo "Monitor: squeue -u $USER"
