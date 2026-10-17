# AmanaMT

Research code for **AmanaMT: Translation Direction Predicts Automatic Metric
Reliability**.

AmanaMT is a multilingual machine-translation metric meta-evaluation spanning
**730,748 segments, 33 languages, three annotation tiers, and 10 automatic
metrics**. It combines professional MQM annotations, crowd-sourced Direct
Assessment, and a clearly separated exploratory synthetic-MQM tier.

[Read the WMT paper](https://www2.statmt.org/wmt26/pdf/2026.wmt-1.42.pdf)

## Main findings

- Translation direction explains substantially more between-language variance
  in COMET reliability than morphological type (`eta²_direction = 0.309`
  versus `eta²_morphology = 0.073`). The six joint direction-by-morphology
  cells explain `eta²_cell = 0.618`.
- Ukrainian's near-zero COMET correlation is explained by a non-news domain
  label, rather than by Ukrainian itself.
- Russian's weak pooled result separates into stronger per-year signals, an
  example of Simpson's paradox caused by combining heterogeneous WMT system
  generations.
- MetricX-24, xCOMET, and COMET outperform surface-overlap baselines across
  resource tiers; their advantage is largest in morphologically complex and
  non-news settings.

These are empirical findings for the benchmark's observed language-direction
cells, not universal claims. In particular, one direction-by-morphology cell is
empty and seven Tier-2 languages do not have human MT annotations.

## Evaluation design

| Tier | Annotation source | Role |
| --- | --- | --- |
| 1a | Professional WMT MQM | Human-annotated core evaluation |
| 1b | WMT Direct Assessment | Broader human-annotated coverage |
| 2 | Llama-3.1-8B synthetic MQM | Exploratory extension only |

Tier 2 is explicitly labeled synthetic and unvalidated against human judgment.
GEMBA is excluded from that tier to avoid judging Llama-generated annotations
with a closely related LLM-based procedure. It is also excluded from DA tiers,
where its MQM-oriented backbone is not directly comparable.

The evaluated suite includes lexical metrics (BLEU, chrF), learned reference-
based metrics (COMET, xCOMET, MetricX-24), reference-free quality estimation,
and GEMBA-MQM where the design permits it. Analyses report Pearson and Spearman
correlations, Kendall variants, soft pairwise accuracy, bootstrap confidence
intervals, direction/morphology cells, and year-stratified robustness checks.

## Repository map

```text
src/mqmbench/
  data/       dataset loading, normalization, and MQM span conversion
  metrics/    lexical, neural, and LLM-based metric adapters
  analysis/   correlations, confidence intervals, and plots
  pipeline.py end-to-end orchestration and cache-aware execution
scripts/
  run_pipeline.py       primary CLI
  slurm/                cluster launchers
tests/
  test_converter.py     MQM aggregation regression tests
settings.toml           experiment configuration
```

Large datasets, model caches, and generated results are intentionally excluded
from Git. The paper's generated tables and claims are produced from pipeline
outputs rather than being hand-entered into analysis code.

## Setup

Python 3.9 or newer is supported. The project uses
[uv](https://docs.astral.sh/uv/), although a standard editable pip install also
works.

```bash
uv venv --python 3.11
uv pip install -e ".[metrics,dev]"
```

For the lightweight MQM conversion tests, only pandas and pytest are needed:

```bash
python -m pytest -q
```

## Running the benchmark

Start with the inexpensive lexical metrics:

```bash
.venv/bin/python scripts/run_pipeline.py \
  --settings settings.toml \
  --only-metrics bleu chrf
```

The GPU-backed workflow is split into cacheable SLURM stages:

```bash
sbatch scripts/slurm/run_nllb.sh
sbatch scripts/slurm/run_synthetic_mqm.sh
sbatch scripts/slurm/run_comet.sh
```

Review `settings.toml` before execution. Model identifiers, enabled metrics,
language pairs, cache paths, and output paths are configuration rather than
library constants. Hugging Face weights must be downloaded where network
access is available before starting offline cluster jobs.

## Reproducibility notes

- The three annotation tiers remain separate in outputs; do not pool synthetic
  and human judgments without preserving the tier label.
- Year-stratified analyses are necessary for multi-year WMT language pairs.
- Some neural metric checkpoints require accepting upstream model licenses.
- Full reproduction requires substantial model storage and GPU time. Unit
  tests exercise data conversion without downloading models.

## License

Code is released under the [MIT License](LICENSE). Upstream datasets and model
weights retain their own licenses and terms of use.
