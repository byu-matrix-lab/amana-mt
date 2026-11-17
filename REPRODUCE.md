# Reproducing the corrected AmanaMT paper (v2)

The paper is in `arxiv_submission/` (the directory name is historical; v2 is an ACL Anthology revision of 2026.wmt-1.42). Every number in it is a LaTeX macro, rendered from `results/paper_stats.json`, which `scripts/generate_paper_stats.py` writes. No number is typed by hand.

There are two levels of reproduction:

- **Audit the analysis (CPU only, about 3 hours).** Start from the released metric scores. This regenerates every correlation, table, figure and macro.
- **Rescore the metrics (GPU).** Rerun the metric models themselves. This needs GPUs and the model checkpoints; see `scripts/slurm/` and `settings.toml` `[metrics]`.

## 1. Data

| What | Where | Used for |
|---|---|---|
| WMT MQM (en-de, en-ru, zh-en, WMT20-22) | Hugging Face `RicardoRei/wmt-mqm-human-evaluation` | Tier 1a labels |
| WMT DA | Hugging Face `RicardoRei/wmt-da-human-evaluation` | Tier 1b labels |
| Google MQM span files (WMT23 he-en, WMT24 en-es) | https://github.com/google/wmt-mqm-human-evaluation, cloned beside this repo (`settings.toml` `wmt_mqm_span_dir = "../wmt-mqm-human-evaluation"`) | he-en and en-es labels |
| mt-metrics-eval v2 data | https://github.com/google/mt-metrics-eval (data release); set the path in the scripts that reference `mt-metrics-eval-v2` | MQM control, reference lines, validation tests |
| Metric scores (`results/scores_*.csv`, 375 MB; 73 MB compressed) | Not in git; ask the authors for `amana_v2_scores.tgz`, then unpack it at the repo root | Starting point for the CPU audit |

The score CSVs are row-aligned with the loaded dataset. `src/mqmbench/pipeline.py` checks the alignment, and refuses to run if it is broken.

## 2. Environment

```sh
python -m venv .venv && .venv/bin/pip install -e .   # Python >= 3.10
export PYTHONPATH=src
```

## 3. Regenerate everything (CPU)

`scripts/slurm/run_regen_wmt_weights.sh` runs these steps on a SLURM cluster. They can also be run by hand from the repo root:

```sh
.venv/bin/python -m pytest tests -q --deselect tests/test_metricx_batch_invariance.py   # MetricX tests need a GPU
.venv/bin/python scripts/run_pipeline.py --settings settings.toml --analysis-only
.venv/bin/python scripts/analyze_direction_separated.py
.venv/bin/python scripts/analyze_surface_similarity.py
.venv/bin/python scripts/validate_against_mt_metrics_eval.py
.venv/bin/python scripts/generate_paper_stats.py          # pass 1
.venv/bin/python scripts/analyze_abjad_mechanism.py
.venv/bin/python scripts/build_metric_reliability_predictor.py
.venv/bin/python scripts/generate_paper_stats.py          # pass 2
export PAPER_DIR=arxiv_submission
.venv/bin/python scripts/render_macros.py
.venv/bin/python scripts/generate_language_table.py
.venv/bin/python scripts/make_presentation_plots.py
for f in arxiv_submission/figures/*.pdf; do cp results/plots/$(basename $f) $f; done
.venv/bin/python scripts/assert_paper_invariants.py       # must end "All checks passed."
```

The MQM control (`sec:mqm_control`) reads the official mt-metrics-eval files directly. To rerun it, run `scripts/audit/mqm_control.py <mtme path>` and `scripts/audit/followup_analyses.py <mtme path>` before step 3.

## 4. Checks on the paper text

- `scripts/assert_paper_invariants.py`: structural and numeric invariants, including that each hand-placed table bold marker matches the data.
- reportkit (https://github.com/byu-matrix-lab/reportkit), cloned two directories up:
  - `env PYTHONPATH=../../reportkit/src python3 -m reportkit claims` checks that each data-dependent sentence matches its predicate, and that retracted wording is absent (`tools/reportkit_claims.py`).
  - `env PYTHONPATH=../../reportkit/src python3 -m reportkit lint` checks that no number is typed by hand.
- `scripts/find_hardcoded_values.py`: a second hardcoded-number scan. Reviewed exceptions are in `notes/v2_scan_exceptions.md`.

## 5. Where each result comes from

| Paper element | Script | Output |
|---|---|---|
| All macros | `scripts/generate_paper_stats.py` | `results/paper_stats.json` |
| Fig. 1 (MQM control) | `make_presentation_plots.py:plot_mqm_control` | `results/plots/presentation_mqm_control.pdf` |
| Fig. 2 (per-pair heatmap) | `make_presentation_plots.py:plot_language_direction_heatmap` | `results/plots/presentation_language_direction_heatmap.pdf` |
| Tables 1-4, 8-9 | `generate_paper_stats.py` (macros); bold markers checked by `assert_paper_invariants.py` | |
| Language table | `scripts/generate_language_table.py` | `arxiv_submission/language_table_generated.tex` |

Corrections relative to the published version are listed in the paper's version note and in `notes/research_log.md` (entries from 2026-11-05).
