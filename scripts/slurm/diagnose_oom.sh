#!/bin/bash --login
#SBATCH --job-name=mqm_diag
#SBATCH --partition=dwmatrix
#SBATCH --qos=matrix
#SBATCH --time=01:00:00
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=192G
#SBATCH --gres=gpu:1
#SBATCH --output=logs/mqm_diag_%j.out

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
cd "$SLURM_SUBMIT_DIR"

nvidia-smi || true

# Force unbuffered Python output so messages appear in log even on SIGKILL
exec .venv/bin/python -u - << 'EOF'
import sys, resource, gc

def rss():
    kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return kb / 1e6  # KB -> GB on Linux

print(f"[MEM] START: {rss():.2f} GB", flush=True)

import pandas as pd
from mqmbench.data.wmt_mqm import load_wmt_mqm
from mqmbench.data.wmt_da import load_wmt_da
from mqmbench.data.flores import load_flores
from mqmbench.data.nllb import generate_hypotheses
from mqmbench.data.synthetic_mqm import generate_synthetic_mqm
from mqmbench.data.converter import annotations_to_sentence_scores
from mqmbench.constants import AnnotationTier
print(f"[MEM] IMPORTS: {rss():.2f} GB", flush=True)

mqm = load_wmt_mqm(lang_pairs=["en-de","zh-en","en-ru","he-en","en-es"])
print(f"[MEM] MQM ({len(mqm)} rows): {rss():.2f} GB", flush=True)

da = load_wmt_da(target_langs=["cs","tr","uk","ha","km","ps","fr","pl","fi","et","is","lt","lv","bn","hi","gu","ta","ja","kk","xh","zu"])
print(f"[MEM] DA ({len(da)} rows): {rss():.2f} GB", flush=True)

fl = load_flores(lang_codes=["sw","ht","lo","th","my","am","ka"])
hyps = generate_hypotheses(fl, model_name="facebook/nllb-200-distilled-600M", cache_dir="data/cache")
synth = generate_synthetic_mqm(hyps, model_name="meta-llama/Llama-3.1-8B-Instruct", cache_dir="data/cache")
synth_scores = annotations_to_sentence_scores(synth)
synth_scores["annotation_tier"] = AnnotationTier.SYNTHETIC_MQM
full = pd.concat([mqm, da, synth_scores], ignore_index=True)
print(f"[MEM] FULL CONCAT ({len(full)} rows, {len(full.columns)} cols): {rss():.2f} GB", flush=True)

ckpt = pd.read_csv("results/scores_checkpoint.csv")
print(f"[MEM] CHECKPOINT ({len(ckpt)} rows, {list(ckpt.columns)}): {rss():.2f} GB", flush=True)

# Try loading xcomet
print("[MEM] Loading xCOMET-XL...", flush=True)
from mqmbench.metrics import comet
sources = full["source"].fillna("").astype(str).tolist()[:100]
hyp_list = full["hypothesis"].fillna("").astype(str).tolist()[:100]
refs = full["reference"].fillna("").astype(str).tolist()[:100]
print(f"[MEM] Before xcomet model load: {rss():.2f} GB", flush=True)
# Just load the model, don't predict on full dataset
from comet import download_model, load_from_checkpoint
model_path = download_model("Unbabel/XCOMET-XL")
print(f"[MEM] After download_model: {rss():.2f} GB", flush=True)
model = load_from_checkpoint(model_path)
print(f"[MEM] After load_from_checkpoint: {rss():.2f} GB", flush=True)
out = model.predict([{"src": s, "mt": h, "ref": r} for s, h, r in zip(sources, hyp_list, refs)], batch_size=8, gpus=1)
print(f"[MEM] After predict (100 samples): {rss():.2f} GB", flush=True)
del model
gc.collect()
import torch; torch.cuda.empty_cache()
print(f"[MEM] After del xcomet: {rss():.2f} GB", flush=True)
EOF
