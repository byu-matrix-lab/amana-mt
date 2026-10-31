"""Load WMT MQM sentence-level scores from HuggingFace.

Dataset: RicardoRei/wmt-mqm-human-evaluation
Schema: lp, src, mt, ref, score, system, annotators, domain, year

The `score` column is an aggregated MQM penalty (negative; 0 = perfect,
more negative = more errors). We convert to quality_score in [0, 1] using
per-language min-max normalization so it is compatible with the unified
quality_score column used throughout the pipeline.

NOTE: This dataset provides sentence-level scores only. Span-level category
annotations (accuracy vs. fluency breakdown) are not available from this
source. The category correlation analysis is disabled for this tier.

Available pairs (confirmed): en-de (WMT20-23), zh-en (WMT20-23),
                              en-ru (WMT21/22), he-en (WMT23), en-es (WMT24).
"""

import logging
from pathlib import Path

import pandas as pd
from datasets import load_dataset

from mqmbench.constants import AnnotationTier
from mqmbench.data.utils import build_segment_id, lang_from_pair, rename_wmt_columns

logger = logging.getLogger(__name__)


def _normalize_per_lang(df: pd.DataFrame) -> pd.DataFrame:
    """Min-max normalize MQM scores to [0, 1] within each language."""
    def _minmax(s: pd.Series) -> pd.Series:
        lo, hi = s.min(), s.max()
        return pd.Series(0.5, index=s.index) if hi == lo else (s - lo) / (hi - lo)

    df = df.copy()
    df["quality_score"] = df.groupby("lang")["mqm_score"].transform(_minmax)
    return df


def load_wmt_mqm(lang_pairs: list[str] | None = None) -> pd.DataFrame:
    """Load Tier 1a sentence-level MQM scores.

    Args:
        lang_pairs: Language pairs to load (e.g. ['en-de', 'zh-en']).
                    If None, loads all available pairs.

    Returns:
        DataFrame with one row per segment, columns:
            segment_id, source, hypothesis, reference, lang,
            mqm_score, quality_score, annotation_tier.
        Does NOT pass through converter.py (sentence-level scores provided directly).
    """
    logger.info("Loading WMT MQM dataset from HuggingFace...")
    df = load_dataset("RicardoRei/wmt-mqm-human-evaluation", split="train").to_pandas()

    available = sorted(df["lp"].unique().tolist())
    logger.info(f"WMT MQM available pairs: {available}")

    if lang_pairs:
        missing = [lp for lp in lang_pairs if lp not in available]
        if missing:
            logger.warning(f"Requested pairs not found in dataset: {missing}")
        df = df[df["lp"].isin(lang_pairs)].copy()

    if df.empty:
        logger.warning("No MQM data matched the requested language pairs.")
        return pd.DataFrame(columns=[
            "segment_id", "source", "hypothesis", "reference",
            "lang", "mqm_score", "quality_score", "annotation_tier",
        ])

    df = rename_wmt_columns(df)
    df = df.rename(columns={"score": "mqm_score"})
    df["segment_id"] = build_segment_id(df)
    df["lang"] = df["lp"].apply(lang_from_pair)
    df = _normalize_per_lang(df)
    df["annotation_tier"] = AnnotationTier.HUMAN_MQM

    # Keep year + system for the medium>high anomaly analysis (multi-year variance).
    keep = ["segment_id", "source", "hypothesis", "reference",
            "lang", "mqm_score", "quality_score", "annotation_tier",
            "domain", "year", "system"]
    return df[[c for c in keep if c in df.columns]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Span-level loader (google/wmt-mqm-human-evaluation TSV files)
# ---------------------------------------------------------------------------
# TSV schema (columns vary slightly by year but core fields are consistent):
#   system, doc, doc_id, seg_id, rater, source, target, category, severity
#
# category values look like "Accuracy/Mistranslation", "Fluency/Grammar", etc.
# severity values: "major", "minor", "neutral" (neutral rows are no-error placeholders)
#
# Download the TSVs from https://github.com/google/wmt-mqm-human-evaluation
# and point data.wmt_mqm_span_dir in settings.toml at the local directory.

_LANG_FROM_FILENAME = {
    "ende": "de", "zhen": "zh", "enru": "ru", "heen": "he", "enes": "es",
    "deen": "de", "ruen": "ru", "enzh": "zh",
}


def build_sacrebleu_ref_lookup(
    lang_pair: str,
    testset: str,
    ref_index: int = 0,
    global_seg_id_offset: int = 0,
    ref_file_override: Path | str | None = None,
) -> dict[int, str]:
    """Build a {globalSegId: reference_text} dict from a cached sacreBLEU dataset.

    Args:
        lang_pair: e.g. "he-en" or "en-es".
        testset: sacreBLEU test set name, e.g. "wmt23" or "wmt24".
        ref_index: Which reference file to use when multiple are available (0 = first).
        global_seg_id_offset: Value added to the 0-indexed line number to get the
            globalSegId. Determined empirically per (testset, lang_pair):
            - "wmt23"/"he-en": offset=0  (globalSegId is 0-indexed, min=0)
            - "wmt24"/"en-es": offset=-1 (globalSegId is 1-indexed with
              globalSegId=1 a canary row) when using ref_file_override below;
              offset=2 was used against sacreBLEU's own news-only "wmt24"
              cache, which is a DIFFERENT, narrower file (see ref_file_override).
        ref_file_override: If given, read reference lines directly from this
            path instead of the sacreBLEU cache. Needed for "wmt24"/"en-es":
            sacreBLEU's own "wmt24" testset only ships the news-domain subset
            of the shared task's actual test set, but WMT24 en-es MQM data
            spans four domains (news/literary/social/speech) sharing one
            globalSegId numbering scheme. Indexing into the news-only cache
            file with that numbering silently returns the wrong reference for
            non-news rows. results/external_refs/wmt24_en-es_multidomain_refA.txt
            is the real, full multi-domain reference release (see its README).

    Returns:
        Dict mapping globalSegId (int) → reference string, or {} on failure.
        The dict can be passed to load_wmt_mqm_spans via ref_lookups.
    """
    import os

    if ref_file_override is not None:
        lines = Path(ref_file_override).read_text(encoding="utf-8").splitlines()
        logger.info(f"    Loaded {len(lines)} refs from override {ref_file_override}")
        return {i + global_seg_id_offset: ref for i, ref in enumerate(lines)}

    # Read pre-cached sacreBLEU ref files directly (avoids XML decompression errors).
    # Files follow the naming convention: ~/.sacrebleu/<testset>/<testset>.<lp>.ref-refA, ref-refB, ...
    ref_labels = ["refA", "refB", "refC"]
    cache_dir = Path(os.path.expanduser("~/.sacrebleu")) / testset
    candidates = []
    for label in ref_labels:
        p = cache_dir / f"{testset}.{lang_pair}.ref-{label}"
        if p.exists():
            candidates.append(p)

    if candidates and ref_index < len(candidates):
        ref_path = candidates[ref_index]
        try:
            lines = ref_path.read_text(encoding="utf-8").splitlines()
            logger.info(f"    Loaded {len(lines)} refs from {ref_path}")
            return {i + global_seg_id_offset: ref for i, ref in enumerate(lines)}
        except Exception as exc:
            logger.warning(f"Could not read {ref_path}: {exc}")

    # Fallback: try sacreBLEU API (may fail on some cluster environments)
    try:
        from sacrebleu.utils import get_reference_files, smart_open
        ref_files = get_reference_files(testset, lang_pair)
        with smart_open(ref_files[ref_index]) as fh:
            lines = [l.strip() for l in fh.readlines()]
        return {i + global_seg_id_offset: ref for i, ref in enumerate(lines)}
    except Exception as exc:
        logger.warning(f"Could not load sacreBLEU refs for {lang_pair}/{testset}: {exc}")
        return {}


# Known offsets: (testset, lang_pair) → global_seg_id_offset for build_sacrebleu_ref_lookup
_SACREBLEU_OFFSETS: dict[tuple[str, str], int] = {
    ("wmt23", "he-en"): 0,
    # sacreBLEU's own "wmt24" cache is news-only; when using it directly the
    # offset is +2 (globalSegId=1 is a canary). When _REF_FILE_OVERRIDES below
    # is used instead (the correct, full multi-domain file), the offset is -1.
    ("wmt24", "en-es"): -1,
}

# (testset, lang_pair) -> path to a reference file that should be used INSTEAD
# of the sacreBLEU cache. Needed for wmt24/en-es: sacreBLEU's "wmt24" testset
# only ships the news-domain subset of the shared task's test set, but en-es
# MQM data spans four domains (news/literary/social/speech) sharing one
# globalSegId numbering scheme -- indexing into the news-only file with that
# numbering silently returns the wrong reference for non-news rows (confirmed:
# ~80% of en-es MQM rows are non-news). This is the official, full
# multi-domain reference release from
# https://github.com/wmt-conference/wmt24-news-systems (txt/references/en-es.refA.txt).
_REF_FILE_OVERRIDES: dict[tuple[str, str], Path] = {
    ("wmt24", "en-es"): Path(__file__).resolve().parents[3]
    / "results" / "external_refs" / "wmt24_en-es_multidomain_refA.txt",
}


def load_wmt_mqm_spans(
    span_dir: str | Path,
    lang_pairs: list[str] | None = None,
    ref_lookups: dict[str, dict[int, str]] | None = None,
) -> pd.DataFrame:
    """Load raw WMT MQM span annotations from Google's TSV release.

    Args:
        span_dir: Directory containing the downloaded TSV files.
        lang_pairs: Language pairs to keep. If None, loads all found files.
        ref_lookups: Optional dict mapping lang code → {globalSegId: reference_text}.
            Used to populate the 'reference' column, which the TSVs do not include.
            Build with build_sacrebleu_ref_lookup().

    Returns:
        DataFrame with span-level annotation rows compatible with converter.py:
            segment_id, source, hypothesis, reference, lang,
            error_type, severity, error_start, error_end, annotation_tier.
    """
    span_dir = Path(span_dir)
    tsv_files = sorted(span_dir.glob("**/*.tsv")) + sorted(span_dir.glob("**/*.csv"))
    if not tsv_files:
        logger.warning(f"No TSV files found in {span_dir}")
        return pd.DataFrame()

    # Build set of target langs from requested pairs
    target_langs: set[str] | None = None
    if lang_pairs:
        target_langs = {lang_from_pair(lp) for lp in lang_pairs}

    frames = []
    for f in tsv_files:
        try:
            raw = pd.read_csv(f, sep="\t", dtype=str, on_bad_lines="skip").fillna("")
        except Exception as exc:
            logger.warning(f"Could not read {f}: {exc}")
            continue

        # Normalise column names across WMT years
        raw.columns = [c.strip().lower().replace(" ", "_") for c in raw.columns]
        col_map = {
            "target": "hypothesis", "mt": "hypothesis", "hyp": "hypothesis",
            "src": "source", "ref": "reference",
            "category": "error_type", "severity": "severity",
            "seg_id": "seg_id",
        }
        raw = raw.rename(columns={k: v for k, v in col_map.items() if k in raw.columns})

        # Infer lang from filename if not a column
        if "lang" not in raw.columns and "lp" not in raw.columns:
            stem = f.stem.lower().replace("-", "").replace("_", "")
            lang = next((v for k, v in _LANG_FROM_FILENAME.items() if k in stem), None)
            if lang is None:
                logger.warning(f"Could not infer lang from filename {f.name}, skipping")
                continue
            raw["lang"] = lang
        elif "lp" in raw.columns:
            raw["lang"] = raw["lp"].apply(lang_from_pair)

        if target_langs and not raw["lang"].isin(target_langs).any():
            continue

        # Filter to requested langs
        if target_langs:
            raw = raw[raw["lang"].isin(target_langs)].copy()

        # Skip files that don't have span annotation columns (e.g. avg_seg_scores files)
        if "severity" not in raw.columns or "hypothesis" not in raw.columns:
            logger.debug(f"Skipping {f.name} — missing severity or hypothesis column")
            continue

        # Map severity: neutral/no-error rows become no_error
        raw["severity"] = raw["severity"].str.strip().str.lower()
        raw["error_type"] = (
            raw["error_type"].str.strip().str.lower()
            .str.replace(r"^[^/]+/", "", regex=True)  # "Accuracy/Mistranslation" → "mistranslation"
        )
        # Drop rows with garbled severity values (e.g. trailing-tab files where JSON
        # blob shifts into the severity column)
        valid_sev = {"major", "minor", "critical", "neutral", "no-error", "no_error", "hotw-test", ""}
        raw = raw[raw["severity"].isin(valid_sev)].copy()
        if raw.empty:
            continue

        no_error_mask = raw["severity"].isin(["", "neutral", "no_error", "no-error"])
        raw.loc[no_error_mask, "severity"] = "no_error"
        raw.loc[no_error_mask, "error_type"] = "no_error"

        # Build segment_id including system so each (system, segment) is unique.
        # WMT TSVs use "system"/"globalsegid" (after lowercasing) as the key columns.
        seg_col = next((c for c in ("globalsegid", "seg_id", "docsegid") if c in raw.columns), None)
        sys_col = "system" if "system" in raw.columns else None
        if seg_col and sys_col:
            raw["segment_id"] = (raw["lang"] + "_" + raw[sys_col].astype(str)
                                 + "_" + raw[seg_col].astype(str))
        elif seg_col:
            raw["segment_id"] = raw["lang"] + "_" + raw[seg_col].astype(str)
        else:
            raw["segment_id"] = raw["lang"] + "_" + raw.index.astype(str)

        # Span character offsets (not in Google TSVs — mark as unknown)
        raw["error_start"] = -1
        raw["error_end"] = -1

        for col in ["source", "hypothesis", "reference"]:
            if col not in raw.columns:
                raw[col] = ""

        # Fill reference from sacreBLEU lookup when available (TSVs omit references).
        if ref_lookups and "lang" in raw.columns and "globalsegid" in raw.columns:
            lang_val = raw["lang"].iloc[0]
            if lang_val in ref_lookups:
                lookup = ref_lookups[lang_val]
                raw["reference"] = (
                    raw["globalsegid"].astype(str)
                    .str.strip()
                    .apply(lambda x: lookup.get(int(x), "") if x.lstrip("-").isdigit() else "")
                )
                filled = (raw["reference"] != "").sum()
                logger.info(f"    Reference lookup: {filled}/{len(raw)} rows filled for {lang_val}")

        raw["annotation_tier"] = AnnotationTier.HUMAN_MQM

        keep = ["segment_id", "source", "hypothesis", "reference", "lang",
                "error_type", "severity", "error_start", "error_end", "annotation_tier"]
        frames.append(raw[[c for c in keep if c in raw.columns]])
        logger.info(f"  Loaded {len(raw)} span rows from {f.name}")

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
