#!/usr/bin/env bash
# Full paper build: SSOT -> macros -> plots -> invariants -> PDF.
#
# This is the ONLY sanctioned way to compile the paper. Running pdflatex
# directly on latex/main.tex risks compiling against a stale
# macros_generated.tex or a stale latex/figures/*.pdf copy left over from a
# previous results/ state -- exactly the kind of silent drift this project's
# SSOT discipline exists to prevent. This script always regenerates
# everything from results/*.csv forward, then copies the regenerated figures
# into latex/figures/ (the directory pdflatex actually reads, which
# make_presentation_plots.py does not write to directly), before invoking
# pdflatex -- so a successful run guarantees the PDF reflects the current
# state of the data pipeline.
#
# Usage (from project root):
#   bash scripts/build_paper.sh
#
# Exits non-zero on the first failure (stats generation, invariant check, or
# LaTeX error) rather than silently continuing to compile with stale/wrong
# inputs.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== 1/7: validate_against_mt_metrics_eval.py (rebuild segment-level external validation) ==="
# Fast (<10s), no bootstrap -- always rerun so results/wmt_baseline_validation_
# segment_level.csv can't silently drift out of sync with the he/es
# checkpoints generate_paper_stats.py reads next.
.venv/bin/python3 scripts/validate_against_mt_metrics_eval.py

echo "=== 2/7: generate_paper_stats.py (rebuild results/paper_stats.json) ==="
# This step is CPU-bound (bootstrap CIs) and can take 10x longer on a busy
# shared login node than on a dedicated allocation -- seen: 93s via
# `sbatch scripts/slurm/run_generate_paper_stats.sh` vs. 12+ minutes (still
# running) directly on a login node with load average 11 and nproc=1. If
# this step is slow, Ctrl-C this script and run that sbatch command instead,
# then resume from step 2 (render_macros.py) once it completes.
.venv/bin/python3 scripts/generate_paper_stats.py

echo "=== 3/7: render_macros.py (write latex/macros_generated.tex) ==="
.venv/bin/python3 scripts/render_macros.py

echo "=== 4/7: make_presentation_plots.py (regenerate all results/plots/*.pdf) ==="
.venv/bin/python3 scripts/make_presentation_plots.py

echo "=== 5/7: sync results/plots/*.pdf -> latex/figures/ ==="
# make_presentation_plots.py writes to results/plots/, but \includegraphics
# in main.tex points at latex/figures/ -- a SEPARATE directory pdflatex never
# touches on its own. Found 2026-09-11: latex/figures/ held PDFs dated over a
# month stale (Aug 7) while results/plots/ had the corrected ones, and every
# earlier "recompile and verify" step in that session silently kept rendering
# the stale copies (including a figure with a retracted claim still visible)
# because nothing ever copied the new files across. Without this step, the
# invariant check below only catches the drift, it can't fix it.
cp results/plots/*.pdf latex/figures/

echo "=== 6/7: assert_paper_invariants.py (must pass before compiling) ==="
.venv/bin/python3 scripts/assert_paper_invariants.py

echo "=== 7/7: pdflatex (two passes) ==="
if ! command -v pdflatex >/dev/null 2>&1; then
    if command -v module >/dev/null 2>&1; then
        # shellcheck disable=SC1091
        source /etc/profile.d/modules.sh 2>/dev/null || true
        module load texlive/2024 2>/dev/null || true
    fi
fi
if ! command -v pdflatex >/dev/null 2>&1 && [ -x /apps/texlive/2026/bin/x86_64-linux/pdflatex ]; then
    # `module load` errors out on this node's Environment-Modules install
    # trying to parse an Lmod-format .lua modulefile ("Magic cookie
    # '#%Module' missing") -- found 2026-09-12. Fall back to PATH directly.
    export PATH="/apps/texlive/2026/bin/x86_64-linux:$PATH"
fi
cd latex
pdflatex -interaction=nonstopmode main.tex > /tmp/build_paper_pass1.log 2>&1 || {
    echo "pdflatex pass 1 FAILED -- see /tmp/build_paper_pass1.log"; tail -40 /tmp/build_paper_pass1.log; exit 1;
}
pdflatex -interaction=nonstopmode main.tex > /tmp/build_paper_pass2.log 2>&1 || {
    echo "pdflatex pass 2 FAILED -- see /tmp/build_paper_pass2.log"; tail -40 /tmp/build_paper_pass2.log; exit 1;
}

if grep -qi "undefined\|! LaTeX Error\|Emergency stop\|Fatal error" /tmp/build_paper_pass2.log; then
    echo "pdflatex reported an error on the second pass -- see /tmp/build_paper_pass2.log"
    grep -i "undefined\|! LaTeX Error\|Emergency stop\|Fatal error" /tmp/build_paper_pass2.log
    exit 1
fi

echo "=== Build complete: latex/main.pdf ==="
grep -i "Output written" /tmp/build_paper_pass2.log
