"""GEMBA-MQM metric.

GEMBA-MQM uses an LLM to directly predict MQM error annotations.
Reference: Kocmi & Federmann (2023) — https://arxiv.org/abs/2303.12402

The LLM is prompted with the source + hypothesis and asked to identify
errors by category and severity, then a penalty score is computed.

This implementation uses a local HuggingFace model (no API key required),
suited for running on the BYU supercomputer with HF_HUB_OFFLINE=1.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

logger = logging.getLogger(__name__)

GEMBA_PROMPT_TEMPLATE = """You are evaluating a machine translation from {source_lang} to {target_lang}.

Source: {source}
Translation: {hypothesis}

List any translation errors in the format:
ERROR: [severity: major|minor] [category: mistranslation|omission|grammar|register|other] [text: ...]

If there are no errors, write: NO ERRORS"""

SEVERITY_PENALTIES = {"major": 5.0, "minor": 1.0}

_MODEL_CACHE: dict = {}


def _load(model_name: str):
    if model_name not in _MODEL_CACHE:
        logger.info(f"Loading GEMBA model: {model_name}")
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        tokenizer.padding_side = "left"
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        device = "cuda" if torch.cuda.is_available() else "cpu"
        # bfloat16 halves VRAM; flash_attention_2 accelerates attention on A100/H100.
        try:
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.bfloat16,
                attn_implementation="flash_attention_2",
            ).to(device)
            logger.info("  Using flash_attention_2")
        except Exception:
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.bfloat16,
            ).to(device)
        model.eval()
        _MODEL_CACHE[model_name] = (tokenizer, model)
    return _MODEL_CACHE[model_name]


def _parse_gemba_output(text: str) -> float:
    """Parse LLM output and compute MQM penalty score."""
    if "NO ERRORS" in text.upper():
        return 0.0
    penalty = 0.0
    for match in re.finditer(r"severity:\s*(major|minor)", text, re.IGNORECASE):
        sev = match.group(1).lower()
        penalty += SEVERITY_PENALTIES.get(sev, 0.0)
    return penalty


def score(
    sources: list[str],
    hypotheses: list[str],
    references: list[str],
    lang: Optional[str] = None,
    model_name: str = "",
    source_lang: str = "English",
    target_lang: str = "the target language",
    batch_size: int = 32,
    max_new_tokens: int = 32,
    max_input_length: int = 384,
    cache_file: Optional[str] = None,
) -> list[float]:
    """Compute GEMBA-MQM scores using a local LLM.

    Args:
        sources: Source sentences.
        hypotheses: MT output sentences.
        references: Reference sentences (unused — GEMBA is reference-free).
        lang: Target language name or code (used in prompt).
        model_name: HuggingFace model ID for the LLM.
        source_lang: Human-readable source language name for prompt.
        target_lang: Human-readable target language name for prompt.
        batch_size: Prompts per forward pass.
        max_new_tokens: Max tokens to generate. 32 covers "NO ERRORS" (2 tokens)
            and ~2 error lines; increase if outputs are getting truncated.
        max_input_length: Truncate prompts to this many tokens.
        cache_file: JSONL path for mid-run checkpointing. Resumes from last saved
            position on restart. Flushed every 500 batches.

    Returns:
        List of MQM penalty scores (0 = perfect, higher = more errors).
        Caller converts via quality_score = 1 / (1 + penalty) so higher = better.
    """
    if not model_name:
        raise ValueError(
            "gemba.score() requires model_name. "
            "Set metrics.gemba_model in settings.toml."
        )

    if lang:
        target_lang = lang

    n = len(sources)
    penalties: list[Optional[float]] = [None] * n

    # Load partial results from cache
    start_idx = 0
    if cache_file is not None:
        cache_path = Path(cache_file)
        if cache_path.exists():
            with cache_path.open() as f:
                for line in f:
                    entry = json.loads(line)
                    idx = entry["idx"]
                    if idx < n:
                        penalties[idx] = entry["penalty"]
            completed = sum(1 for p in penalties if p is not None)
            if completed > 0:
                logger.info(f"GEMBA resuming from cache: {completed}/{n} segments already scored")
            start_idx = next((i for i, p in enumerate(penalties) if p is None), n)

    if start_idx >= n:
        logger.info("GEMBA: all segments already scored from cache")
        return [p if p is not None else 0.0 for p in penalties]

    tokenizer, model = _load(model_name)
    device = next(model.parameters()).device

    prompts = [
        GEMBA_PROMPT_TEMPLATE.format(
            source_lang=source_lang,
            target_lang=target_lang,
            source=src,
            hypothesis=hyp,
        )
        for src, hyp in zip(sources, hypotheses)
    ]

    save_every = 500
    batches_since_save = 0
    cache_handle = open(cache_file, "a") if cache_file is not None else None

    try:
        for i in range(start_idx, n, batch_size):
            batch_prompts = prompts[i : i + batch_size]
            enc = tokenizer(
                batch_prompts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=max_input_length,
            ).to(device)

            with torch.no_grad():
                out_ids = model.generate(
                    **enc,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    pad_token_id=tokenizer.eos_token_id,
                )

            # Decode only the newly generated tokens, not the input prompt
            new_ids = out_ids[:, enc["input_ids"].shape[1]:]
            decoded = tokenizer.batch_decode(new_ids, skip_special_tokens=True)

            for j, text in enumerate(decoded):
                penalty = _parse_gemba_output(text)
                global_idx = i + j
                penalties[global_idx] = penalty
                if cache_handle is not None:
                    cache_handle.write(json.dumps({"idx": global_idx, "penalty": penalty}) + "\n")

            batches_since_save += 1
            if cache_handle is not None and batches_since_save >= save_every:
                cache_handle.flush()
                batches_since_save = 0

            if (i - start_idx) % (batch_size * 200) == 0:
                done = i - start_idx + len(decoded)
                logger.info(f"GEMBA: {done + start_idx}/{n} segments scored")
    finally:
        if cache_handle is not None:
            cache_handle.flush()
            cache_handle.close()

    return [p if p is not None else 0.0 for p in penalties]
