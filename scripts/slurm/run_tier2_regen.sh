#!/bin/bash --login

#SBATCH --job-name=mqmbench_tier2
#SBATCH --partition=cs
#SBATCH --qos=cs
#SBATCH --time=12:00:00
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=128G
#SBATCH --gres=gpu:1
#SBATCH --output=logs/mqmbench_tier2_%j.out

# Regenerate Tier 2 synthetic MQM annotations with a fixed prompt.
# The prior run (Llama-3.1-8B) had a bug: return_full_text defaulted to True,
# so the prompt text (which contains "NO ERRORS") was in generated_text, causing
# every output to be classified as no_error. Fixed in synthetic_mqm.py.
#
# Prerequisite: delete old caches before submitting:
#   rm data/cache/synthetic_mqm_*.jsonl
#
# After this job finishes, submit run_analysis_only.sh to regenerate results.

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

cd "$SLURM_SUBMIT_DIR"

nvidia-smi || echo "nvidia-smi not available"

srun .venv/bin/python -c "
import logging
logging.basicConfig(level=logging.INFO)
import sys
sys.path.insert(0, 'src')
from mqmbench.config import init_settings, settings
from mqmbench.data.flores import load_flores
from mqmbench.data.nllb import generate_hypotheses
from mqmbench.data.synthetic_mqm import generate_synthetic_mqm
from pathlib import Path

init_settings('settings.toml')
tier2_langs = list(settings.data.tier2_langs)
cache_dir = settings.data.cache_dir

# Verify caches are cleared
import os
for lang in tier2_langs:
    cache_file = Path(cache_dir) / f'synthetic_mqm_{lang}.jsonl'
    if cache_file.exists():
        print(f'WARNING: cache exists for {lang} — delete it to force regeneration', flush=True)

try:
    flores_df = load_flores(lang_codes=tier2_langs)
except Exception as e:
    print(f'FLORES+ unavailable ({e}); using NLLB cache directly', flush=True)
    from mqmbench.data.utils import read_jsonl_cache
    hyp_rows = []
    for lang in tier2_langs:
        cache_file = Path(cache_dir) / f'nllb_hypotheses_{lang}.jsonl'
        if cache_file.exists():
            hyp_rows.extend(read_jsonl_cache(cache_file))
    import pandas as pd
    flores_df = pd.DataFrame()
    flores_hyp_df = pd.DataFrame(hyp_rows)
    generate_synthetic_mqm(flores_hyp_df, model_name=settings.metrics.gemba_model,
                           cache_dir=cache_dir)
    print('Done.', flush=True)
    exit(0)

flores_hyp_df = generate_hypotheses(flores_df, model_name=settings.data.nllb_model,
                                    cache_dir=cache_dir)
generate_synthetic_mqm(flores_hyp_df, model_name=settings.metrics.gemba_model,
                       cache_dir=cache_dir)
print('Synthetic MQM regeneration complete.', flush=True)
"
