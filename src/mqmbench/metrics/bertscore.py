"""BERTScore metric.

Uses microsoft/mdeberta-v3-base by default for multilingual coverage.
F1 scores are returned (range roughly [0, 1], higher is better).
"""

from typing import Optional

import bert_score


# bert_score caches all sentence embeddings in a stats_dict before scoring,
# so passing all 707K rows at once accumulates ~130GB of embeddings in RAM.
# Chunking keeps peak usage to ~2GB per chunk.
_CHUNK_SIZE = 10_000


def score(
    sources: list[str],
    hypotheses: list[str],
    references: list[str],
    lang: Optional[str] = None,
    model_type: str = "microsoft/mdeberta-v3-base",
    batch_size: int = 32,
) -> list[float]:
    """Compute BERTScore F1 for each hypothesis/reference pair.

    Args:
        sources: Source sentences (unused).
        hypotheses: MT output sentences.
        references: Human reference sentences.
        lang: BCP-47 language code — passed to bert_score if model_type is None.
        model_type: HuggingFace model ID. If provided, overrides lang-based selection.
        batch_size: Batch size for encoding.

    Returns:
        List of BERTScore F1 values in approximately [0, 1].
    """
    import ctypes
    import gc

    # glibc holds freed pages and doesn't return them to the OS after gc.collect().
    # malloc_trim(0) forces page release so RSS doesn't grow across chunks.
    _libc = ctypes.cdll.LoadLibrary("libc.so.6")

    all_f1: list[float] = []
    for start in range(0, len(hypotheses), _CHUNK_SIZE):
        h_chunk = hypotheses[start : start + _CHUNK_SIZE]
        r_chunk = references[start : start + _CHUNK_SIZE]
        _, _, f1 = bert_score.score(
            h_chunk,
            r_chunk,
            model_type=model_type,
            lang=None if model_type else lang,
            batch_size=batch_size,
            verbose=False,
        )
        all_f1.extend(f1.tolist())
        gc.collect()
        _libc.malloc_trim(0)
    return all_f1
