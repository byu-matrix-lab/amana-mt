"""Regression tests for the human-label fixes of 2026-11-09.

1. MQM normalization is within (language, year): en-ru 2021 (100-point scale)
   and 2022 (penalty scale) must not be ranked against each other raw.
2. Span-TSV fallback (he-en, en-es): quote-safe parsing, <v> markup stripped,
   exactly one row per (system, segment), no canary / refA rows, correct
   reference line, and agreement with the official mt-metrics-eval MQM scores.

The span tests need the Google TSVs and mt-metrics-eval on disk; skipped otherwise.
    .venv/bin/python -m pytest tests/test_label_fixes.py -q
"""
import csv
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr

from mqmbench.data.wmt_mqm import _normalize_per_lang, load_span_fallback_scores

ROOT = Path(__file__).resolve().parents[1]
SPAN_DIR = ROOT.parent / "wmt-mqm-human-evaluation"
MTME = Path.home() / "nobackup/archive/mtme/mt-metrics-eval-v2"
TSV = {
    "he": SPAN_DIR / "generalMT2023/heen/mqm_generalMT2023_heen.tsv",
    "es": SPAN_DIR / "generalMT2024/mqm_generalMT2024_enes.tsv",
}
# (edition, lp, line offset: mtme line = globalSegId - offset)
MTME_SPEC = {"he": ("wmt23", "he-en", 0), "es": ("wmt24", "en-es", 1)}


def test_normalization_is_within_year():
    # 2021 on a 100-point scale, 2022 on a penalty scale. A good 2022
    # translation (0) must be able to outrank a bad 2021 one (-400).
    df = pd.DataFrame({
        "lang": ["ru"] * 6,
        "year": [2021, 2021, 2021, 2022, 2022, 2022],
        "mqm_score": [100.0, 50.0, -400.0, 0.0, -1.0, -65.0],
    })
    q = _normalize_per_lang(df)["quality_score"].tolist()
    # Same rank pattern in both years -> same normalized values.
    assert q[:3] == q[3:]
    assert q[0] > q[1] > q[2]
    assert q[3] > q[2]  # the old pooled min-max put every 2022 row below most of 2021


@pytest.fixture(scope="module")
def spans():
    if not all(p.exists() for p in TSV.values()):
        pytest.skip("span TSVs not available")
    return load_span_fallback_scores(SPAN_DIR, ["he-en", "en-es"])


def _units(lang):
    d = pd.read_csv(TSV[lang], sep="\t", dtype=str, quoting=csv.QUOTE_NONE, keep_default_na=False)
    d = d[(d.system != "refA") & (d.doc.str.lower() != "canary")]
    return d.groupby(["system", "globalSegId"]).ngroups


@pytest.mark.parametrize("lang", ["he", "es"])
def test_one_row_per_unit(spans, lang):
    sub = spans[spans.lang == lang]
    assert len(sub) == _units(lang)
    assert sub.segment_id.is_unique


def test_no_markup_canary_or_refA(spans):
    assert not spans.hypothesis.str.contains(r"</?v>").any()
    assert not spans.source.str.contains("CANARY").any()
    assert not spans.segment_id.str.contains("_refA_").any()
    assert (spans.reference != "").all()


def _mtme_lines(edition, lp, kind):
    path = MTME / edition / ("sources" if kind == "src" else "references") / (
        f"{lp}.txt" if kind == "src" else f"{lp}.refA.txt")
    return path.read_text(encoding="utf-8").split("\n")


@pytest.mark.parametrize("lang", ["he", "es"])
def test_reference_is_aligned_with_source(spans, lang):
    if not MTME.exists():
        pytest.skip("mt-metrics-eval not available")
    edition, lp, off = MTME_SPEC[lang]
    src, ref = _mtme_lines(edition, lp, "src"), _mtme_lines(edition, lp, "ref")
    sub = spans[spans.lang == lang]
    g = sub.segment_id.str.rsplit("_", n=1).str[-1].astype(int) - off
    assert (sub.source.str.strip().values == [src[i].strip() for i in g]).mean() > 0.99
    assert (sub.reference.values == [ref[i] for i in g]).all()


@pytest.mark.parametrize("lang", ["he", "es"])
def test_agrees_with_official_mqm(spans, lang):
    if not MTME.exists():
        pytest.skip("mt-metrics-eval not available")
    edition, lp, off = MTME_SPEC[lang]
    off_df = pd.read_csv(MTME / edition / "human-scores" / f"{lp}.mqm.seg.score", sep="\t",
                         header=None, names=["system", "score"], na_values=["None"])
    off_df["line"] = off_df.groupby("system").cumcount()
    sub = spans[spans.lang == lang].copy()
    parts = sub.segment_id.str.split("_")
    sub["system"] = parts.str[1:-1].str.join("_")
    sub["line"] = parts.str[-1].astype(int) - off
    m = sub.merge(off_df, on=["system", "line"]).dropna(subset=["score"])
    assert len(m) > 0.95 * len(sub)
    rho = spearmanr(-m.error_penalty, m.score)[0]
    assert rho > 0.98, rho
    # 2026-11-10: with the official WMT weights the segment scores must match exactly
    # (the earlier critical=25 / punctuation=1 weights matched only ~90-96%).
    exact = np.isclose(-m.error_penalty.values, m.score.values, atol=1e-6).mean()
    assert exact > 0.999, exact
