"""Shared utilities for WMT and FLORES data loaders."""

import json
from pathlib import Path

import pandas as pd

# Single source of truth for ISO-639 → BCP-47 language code mapping.
# Used by both flores.py (FLORES-200 dataset names) and nllb.py (translation targets).
ISO_TO_BCP47: dict[str, str] = {
    # Tier 2 — low-resource synthetic
    "sw": "swh_Latn",   # Swahili
    "ht": "hat_Latn",   # Haitian Creole
    "lo": "lao_Laoo",   # Lao
    "th": "tha_Thai",   # Thai
    "my": "mya_Mymr",   # Burmese
    "am": "amh_Ethi",   # Amharic
    "ka": "kat_Geor",   # Georgian
    # Tier 1b — WMT DA medium/low
    "es": "spa_Latn",   # Spanish
    "cs": "ces_Latn",   # Czech
    "tr": "tur_Latn",   # Turkish
    "uk": "ukr_Cyrl",   # Ukrainian
    "ha": "hau_Latn",   # Hausa
    "km": "khm_Khmr",   # Khmer
    "ps": "pbt_Arab",   # Pashto
}

# WMT datasets use src/mt/ref; our pipeline uses source/hypothesis/reference.
_WMT_COLUMN_RENAME = {"src": "source", "mt": "hypothesis", "ref": "reference"}


def lang_from_pair(lp: str) -> str:
    """Return the non-English side of a WMT language pair.

    For X-en pairs (e.g. zh-en, he-en) returns the source language (zh, he).
    For en-X pairs (e.g. en-de, en-ru, en-es) returns the target language (de, ru, es).
    """
    parts = lp.split("-")
    return parts[0] if parts[-1] == "en" else parts[-1]


def rename_wmt_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename WMT src/mt/ref columns to source/hypothesis/reference."""
    rename = {k: v for k, v in _WMT_COLUMN_RENAME.items() if k in df.columns}
    return df.rename(columns=rename) if rename else df


def build_segment_id(df: pd.DataFrame) -> pd.Series:
    """Construct a unique segment_id from available WMT identifier columns.

    Some WMT DA releases (e.g. RicardoRei/wmt-da-human-evaluation) provide none
    of doc_id/seg_id/sys_name, and lp/year/domain are themselves constant within
    a language (e.g. all of uk-en is lp="uk-en", year=2022, domain="other") --
    the naive join above then collapses to a single repeated ID for every row in
    that language (found via advisor review, 2026-09-11: 16,470 Ukrainian rows
    sharing one segment_id). That didn't corrupt the merges that use it because
    they fall back to positional alignment when segment_id is non-unique, but
    it's a landmine: silently correct only as long as row order never changes.
    Append a per-group occurrence counter so segment_id is always genuinely
    unique, regardless of which identifier columns are actually present.
    """
    id_cols = [c for c in ("lp", "year", "domain", "doc_id", "seg_id", "sys_name")
               if c in df.columns]
    if id_cols:
        base = df[id_cols].astype(str).agg("_".join, axis=1)
    else:
        base = pd.Series("row", index=df.index)
    occurrence = base.groupby(base).cumcount().astype(str)
    return base + "_" + occurrence


def read_jsonl_cache(path: Path) -> list[dict]:
    """Read a JSONL cache file, returning a list of dicts."""
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def write_jsonl_cache(path: Path, items: list[dict]) -> None:
    """Write a list of dicts to a JSONL cache file."""
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item) + "\n")
