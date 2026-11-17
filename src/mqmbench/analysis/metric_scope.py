"""Which segments each metric is reported on (corrected paper v2, 2026-11-10).

Single source of truth for two decisions made after the 2026-11-10 code audit:

* GEMBA is excluded from all analyses. Its prompt-echo parsing bug was fixed,
  but the scores are still degenerate: 99.6% of the MQM segments score 1.0
  ("no errors"), it was never run on he/es, and the prompt hard-codes English
  as the source language.
* BLEURT (Elron/bleurt-large-512, a port of English BLEURT-large) is excluded
  (2026-11-16). It was briefly reported on English-target segments only, but a
  metric that covers a different subset of every language is not comparable
  with the others. ENGLISH_TARGET_ONLY and in_scope keep the target-language
  logic for any future English-only metric.

Every reader of results/scores_<metric>.csv that feeds the paper applies these
rules through ``apply_metric_scope``, so they cannot drift between scripts.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

EXCLUDED_METRICS = frozenset({"gemba", "bleurt"})
ENGLISH_TARGET_ONLY = frozenset({"bleurt"})

# segment_id prefixes that are not "<src>-<tgt>": the he-en / en-es span block
# and the Tier 2 FLORES rows (en->X).
_PREFIX_TARGET = {"he": "en", "es": "es", "flores": None}


def target_language(segment_id: pd.Series) -> pd.Series:
    """Target language code from a segment_id's leading language pair."""
    prefix = segment_id.astype(str).str.split("_", n=1).str[0]
    tgt = prefix.where(~prefix.str.contains("-"), prefix.str.split("-").str[-1])
    mapped = prefix.map(_PREFIX_TARGET)
    has_map = prefix.isin(list(_PREFIX_TARGET))
    out = tgt.where(~has_map, mapped)
    unknown = ~prefix.str.contains("-") & ~has_map
    if unknown.any():
        raise ValueError(f"cannot infer target language for segment_id prefixes "
                         f"{sorted(prefix[unknown].unique())[:5]}")
    return out


def in_scope(metric: str, segment_id: pd.Series) -> np.ndarray:
    """Boolean mask of rows on which ``metric`` is reported."""
    if metric in EXCLUDED_METRICS:
        return np.zeros(len(segment_id), dtype=bool)
    if metric in ENGLISH_TARGET_ONLY:
        return (target_language(segment_id) == "en").to_numpy()
    return np.ones(len(segment_id), dtype=bool)


def apply_metric_scope(df: pd.DataFrame, metric: str, id_col: str = "segment_id") -> pd.DataFrame:
    """Copy of ``df`` with ``metric`` set to NaN on out-of-scope rows."""
    out = df.copy()
    if metric in out.columns:
        out.loc[~in_scope(metric, out[id_col]), metric] = np.nan
    return out
