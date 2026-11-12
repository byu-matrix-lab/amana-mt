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

import csv
import logging
from pathlib import Path

import pandas as pd
from datasets import load_dataset

from mqmbench.constants import AnnotationTier
from mqmbench.data.utils import build_segment_id, lang_from_pair, rename_wmt_columns

logger = logging.getLogger(__name__)


def _normalize_per_lang(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize MQM scores to [0, 1] within each (language, WMT year).

    Fixed 2026-11-09. The HF dataset does not use one scale across years:
    en-ru 2021 is on a 100-point scale (100 = perfect, min -400) while en-ru
    2022 and every en-de / zh-en year are negative penalties (0 = perfect).
    The earlier version min-maxed all years of a language together, so for
    Russian 96% of 2021 rows ranked above every 2022 row regardless of
    quality, which produced the "Simpson's paradox" in the published paper.

    Within one (language, year) any monotone transform leaves Spearman
    unchanged; across years we use the percentile rank (ties averaged), which
    puts every year on a common [0, 1] scale and is robust to the -400
    outlier that would dominate a min-max.
    """
    df = df.copy()
    keys = ["lang", "year"] if "year" in df.columns else ["lang"]
    df["quality_score"] = df.groupby(keys)["mqm_score"].rank(method="average", pct=True)
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
            - "wmt24"/"en-es": offset=+1 (globalSegId is 1-indexed with
              globalSegId=1 a canary row; line = globalSegId - 1). See the
              comment on _SACREBLEU_OFFSETS for how this was verified.
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
    # The lookup maps key = line_index + offset, so lookup[globalSegId] is
    # line (globalSegId - offset). Verified 2026-11-09 against mt-metrics-eval
    # by matching TSV source text to the aligned sources/<lp>.txt:
    #   he-en: TSV source(g) == wmt23 sources line g     (820/820)  -> offset 0
    #   en-es: TSV source(g) == wmt24 sources line g - 1 (622/623; the miss is
    #          the globalSegId=1 canary)                            -> offset +1
    # The earlier value -1 (commit 7a65176) returned line g + 1, i.e. every
    # en-es reference two lines off. The published en-es scores predate that
    # commit and used the correct lines.
    ("wmt23", "he-en"): 0,
    ("wmt24", "en-es"): 1,
}

# (testset, lang_pair) -> path to a reference file that should be used INSTEAD
# of the sacreBLEU cache. wmt24/en-es: the official multi-domain reference
# release from https://github.com/wmt-conference/wmt24-news-systems
# (txt/references/en-es.refA.txt). Verified 2026-11-09 identical, line for
# line (999/999), to mt-metrics-eval wmt24 references/en-es.refA.txt.
# (An older comment here said sacreBLEU's own "wmt24" cache is news-only; the
# 2026-11-07 data audit found it has 997 lines covering all four domains, so
# that was not the real reason. The override is kept because it is verified.)
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
            # QUOTE_NONE (fixed 2026-11-09): the TSVs are not CSV-quoted, and
            # pandas' default quoting treated '"' inside source/target text as
            # field quotes, merging and dropping lines (he-en: 13,665 lines
            # read as 12,560 rows, 9.7% of (system, segment) units lost).
            raw = pd.read_csv(f, sep="\t", dtype=str, quoting=csv.QUOTE_NONE,
                              keep_default_na=False, on_bad_lines="skip").fillna("")
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

        # hotw-test rows are rater attention checks ("hands on the wheel"),
        # not annotations; they have no MQM weight. Drop them.
        raw = raw[raw["severity"] != "hotw-test"].copy()

        # The target column wraps each annotated error span in <v>...</v>, so
        # the same translation appears with different markup on each error
        # row. Strip it (fixed 2026-11-09): with the markup left in, (a) every
        # metric was scored on text that marks where the human found errors,
        # and (b) one translation with k errors became k "segments", each
        # carrying only one error's penalty.
        raw["hypothesis"] = raw["hypothesis"].str.replace(r"</?v>", "", regex=True)

        # Drop canary rows (WMT24 en-es globalSegId=1, doc "canary";
        # source == hypothesis == reference) and the human reference "system"
        # refA, which would be scored against itself (refA is the reference).
        if "doc" in raw.columns:
            raw = raw[raw["doc"].str.lower() != "canary"]
        if "source" in raw.columns:
            raw = raw[~raw["source"].str.contains("CANARY", regex=False)]
        if "system" in raw.columns:
            raw = raw[raw["system"] != "refA"]
        raw = raw.copy()
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


# WMT edition for each pair that goes through the span-TSV fallback.
SPAN_FALLBACK_TESTSETS: dict[str, str] = {"he-en": "wmt23", "en-es": "wmt24"}


def load_span_fallback_scores(span_dir: str | Path, lang_pairs: list[str]) -> pd.DataFrame:
    """Sentence-level MQM rows for the pairs that come from Google's span TSVs.

    Single shared implementation (2026-11-09) used by pipeline.py and
    scripts/generate_paper_stats.py, which previously each built their own
    reference lookups with their own copy of the offsets.

    Returns one row per (system, globalSegId) with segment_id
    "<lang>_<system>_<globalSegId>" (unique; raises if not).
    """
    from mqmbench.data.converter import annotations_to_sentence_scores

    lang_pairs = [lp for lp in lang_pairs if lp in SPAN_FALLBACK_TESTSETS]
    ref_lookups: dict[str, dict[int, str]] = {}
    for lp in lang_pairs:
        testset = SPAN_FALLBACK_TESTSETS[lp]
        lookup = build_sacrebleu_ref_lookup(
            lp, testset,
            global_seg_id_offset=_SACREBLEU_OFFSETS.get((testset, lp), 0),
            ref_file_override=_REF_FILE_OVERRIDES.get((testset, lp)),
        )
        if not lookup:
            raise RuntimeError(f"No reference lookup for {lp}/{testset}")
        ref_lookups[lang_from_pair(lp)] = lookup

    spans = load_wmt_mqm_spans(span_dir, lang_pairs=lang_pairs, ref_lookups=ref_lookups)
    if spans.empty:
        return pd.DataFrame()
    n_units = spans["segment_id"].nunique()
    scores = annotations_to_sentence_scores(spans, scheme="wmt")  # official WMT weights (2026-11-10)
    if len(scores) != n_units or scores["segment_id"].duplicated().any():
        raise RuntimeError(
            f"span conversion produced {len(scores)} rows for {n_units} (system, segment) "
            "units; one unit must map to exactly one row"
        )
    empty_ref = (scores["reference"] == "").sum()
    if empty_ref:
        raise RuntimeError(f"{empty_ref} span rows have an empty reference")
    scores["annotation_tier"] = AnnotationTier.HUMAN_MQM
    return scores
