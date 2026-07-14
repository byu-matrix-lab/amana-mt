"""COMET and xCOMET metrics via unbabel-comet.

COMET (wmt22-comet-da): reference-based, scores in approximately [0, 1].
xCOMET (XCOMET-XL): also provides MQM-style error span detection.
"""

import ctypes
import gc
import json
from pathlib import Path
from typing import Optional

_libc = ctypes.cdll.LoadLibrary("libc.so.6")

from comet import download_model, load_from_checkpoint

# Lightning's predict() accumulates all batch output dicts before returning.
# Chunking limits how many batches accumulate per call.
_CHUNK_SIZE = 10_000


def _load_model(model_name: str):
    model_path = download_model(model_name)
    return load_from_checkpoint(model_path)


def score(
    sources: list[str],
    hypotheses: list[str],
    references: list[str],
    lang: Optional[str] = None,
    model_name: str = "Unbabel/wmt22-comet-da",
    batch_size: int = 16,
    gpus: int = 0,
    cache_file: Optional[str] = None,
) -> list[float]:
    """Compute COMET scores for each (source, hypothesis, reference) triple.

    Args:
        sources: Source sentences.
        hypotheses: MT output sentences.
        references: Human reference sentences.
        lang: Target language code (unused — COMET is language-agnostic).
        model_name: COMET model to use.
        batch_size: Batch size.
        gpus: Number of GPUs (0 = CPU).
        cache_file: Optional JSONL path for per-chunk checkpointing. On resume,
            already-completed chunks are skipped. Useful for slow models (xCOMET)
            that may time out and need to be restarted.

    Returns:
        List of COMET scores, approximately in [0, 1].
    """
    n = len(sources)
    all_scores: list[Optional[float]] = [None] * n

    # Load partial results from cache
    start_chunk = 0
    if cache_file is not None:
        cache_path = Path(cache_file)
        if cache_path.exists():
            with cache_path.open() as f:
                for line in f:
                    entry = json.loads(line)
                    idx, val = entry["idx"], entry["score"]
                    if idx < n:
                        all_scores[idx] = val
            completed = sum(1 for s in all_scores if s is not None)
            if completed > 0:
                import logging
                logging.getLogger(__name__).info(
                    f"COMET resuming from cache: {completed}/{n} scores loaded"
                )
            # Resume from the first chunk that has any None
            start_chunk = next(
                (i // _CHUNK_SIZE for i, s in enumerate(all_scores) if s is None),
                (n + _CHUNK_SIZE - 1) // _CHUNK_SIZE,
            )

    model = _load_model(model_name)
    cache_handle = open(cache_file, "a") if cache_file is not None else None

    try:
        for chunk_idx, start in enumerate(range(0, n, _CHUNK_SIZE)):
            if chunk_idx < start_chunk:
                continue
            data = [
                {"src": src, "mt": hyp, "ref": ref}
                for src, hyp, ref in zip(
                    sources[start : start + _CHUNK_SIZE],
                    hypotheses[start : start + _CHUNK_SIZE],
                    references[start : start + _CHUNK_SIZE],
                )
            ]
            output = model.predict(data, batch_size=batch_size, gpus=gpus)
            for i, s in enumerate(output.scores):
                all_scores[start + i] = s
                if cache_handle is not None:
                    cache_handle.write(json.dumps({"idx": start + i, "score": s}) + "\n")
            if cache_handle is not None:
                cache_handle.flush()
            gc.collect()
            _libc.malloc_trim(0)
    finally:
        if cache_handle is not None:
            cache_handle.close()

    return [s if s is not None else 0.0 for s in all_scores]


def score_kiwi(
    sources: list[str],
    hypotheses: list[str],
    model_name: str = "Unbabel/wmt22-cometkiwi-da",
    batch_size: int = 16,
    gpus: int = 0,
) -> list[float]:
    """Compute COMET-Kiwi (reference-free QE) scores.

    Uses only source + hypothesis — no reference required. Useful for
    low-resource languages where reference quality may be poor.
    """
    model = _load_model(model_name)
    all_scores: list[float] = []
    for start in range(0, len(sources), _CHUNK_SIZE):
        data = [
            {"src": src, "mt": hyp}
            for src, hyp in zip(
                sources[start : start + _CHUNK_SIZE],
                hypotheses[start : start + _CHUNK_SIZE],
            )
        ]
        output = model.predict(data, batch_size=batch_size, gpus=gpus)
        all_scores.extend(output.scores)
        gc.collect()
        _libc.malloc_trim(0)
    return all_scores


def score_xcomet(
    sources: list[str],
    hypotheses: list[str],
    references: list[str],
    lang: Optional[str] = None,
    model_name: str = "Unbabel/XCOMET-XL",
    batch_size: int = 8,
    gpus: int = 0,
    cache_file: Optional[str] = None,
) -> list[float]:
    """Compute xCOMET scores (same interface as score(), separate function for model clarity)."""
    return score(
        sources, hypotheses, references,
        lang=lang,
        model_name=model_name,
        batch_size=batch_size,
        gpus=gpus,
        cache_file=cache_file,
    )
