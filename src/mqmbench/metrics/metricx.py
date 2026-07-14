"""MetricX-24 metric.

MetricX-24 (Juraska et al., WMT 2024) is Google's top-performing MT metric.
It is an mT5-based encoder-decoder regression model: the decoder produces a
single token (vocab position 250089, <extra_id_10>) whose logit is the score.

Scores are in [0, 25] where 0 = perfect and 25 = worst. We return
(25 - raw) so that higher = better, consistent with all other pipeline metrics.

Reference:
  Juraska et al. (2024). MetricX-24: The Google Submission to the WMT 2024
  Metrics Shared Task. ACL Anthology 2024.wmt-1.35, pp. 492–504.

Model: google/metricx-24-hybrid-large-v2p6-bfloat16
  (~580M params, bfloat16, ~1.2 GB on disk)
  Hybrid = reference-based and reference-free (QE) from the same checkpoint.

Input format (reference-based):
  "source: {src} candidate: {hyp} reference: {ref}"
  (EOS token removed from end before passing to encoder)
"""

import logging
from typing import Optional

import ctypes
import gc

import torch
from transformers import AutoTokenizer, MT5ForConditionalGeneration

_libc = ctypes.cdll.LoadLibrary("libc.so.6")

logger = logging.getLogger(__name__)

_MODEL_CACHE: dict = {}

# Vocab position for <extra_id_10> in the mT5 sentencepiece vocabulary.
# MetricX uses this token's logit as the scalar quality score.
_EXTRA_ID_10 = 250089


def _load(model_name: str):
    if model_name not in _MODEL_CACHE:
        logger.info(f"Loading MetricX model: {model_name}")
        # bfloat16 variant has no bundled tokenizer; use mt5-large's.
        tokenizer = AutoTokenizer.from_pretrained("google/mt5-large")
        model = MT5ForConditionalGeneration.from_pretrained(
            model_name, torch_dtype=torch.bfloat16
        )
        model.eval()
        _MODEL_CACHE[model_name] = (tokenizer, model)
    return _MODEL_CACHE[model_name]


def score(
    sources: list[str],
    hypotheses: list[str],
    references: list[str],
    model_name: str = "google/metricx-24-hybrid-large-v2p6-bfloat16",
    batch_size: int = 32,
    max_length: int = 1024,
    device: Optional[str] = None,
) -> list[float]:
    """Compute MetricX-24 scores.

    Args:
        sources: Source sentences.
        hypotheses: MT output sentences.
        references: Human reference translations.
        model_name: HuggingFace model ID.
        batch_size: Tokenization + inference batch size.
        max_length: Max input token length (MetricX uses 1024).
        device: 'cuda', 'cpu', or None (auto-detect).

    Returns:
        List of floats in [0, 25] where higher = better quality
        (raw MetricX scores are subtracted from 25 so direction is consistent
        with COMET/BLEURT — higher = better).
    """
    tokenizer, model = _load(model_name)

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)

    inputs_text = [
        f"source: {src} candidate: {hyp} reference: {ref}"
        for src, hyp, ref in zip(sources, hypotheses, references)
    ]

    scores_out = []
    for i in range(0, len(inputs_text), batch_size):
        batch = inputs_text[i : i + batch_size]
        enc = tokenizer(
            batch,
            max_length=max_length,
            truncation=True,
            padding=True,
            return_tensors="pt",
        )
        # Remove EOS token (as per official MetricX inference)
        input_ids = enc["input_ids"][:, :-1].to(device)
        attention_mask = enc["attention_mask"][:, :-1].to(device)

        # Decoder needs a single dummy input token (pad=0); MT5 then generates
        # logits over the vocabulary at that one position. We read token 250089
        # (<extra_id_10>) exactly as MetricX-24 does.
        decoder_input_ids = torch.zeros(
            input_ids.size(0), 1, dtype=torch.long, device=device
        )
        with torch.no_grad():
            out = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                decoder_input_ids=decoder_input_ids,
            )
        raw = out.logits[:, 0, _EXTRA_ID_10].clamp(0, 25)
        # Convert from "lower=better" to "higher=better"
        scores_out.extend((25.0 - raw).cpu().float().tolist())
        gc.collect()
        _libc.malloc_trim(0)

    return scores_out
