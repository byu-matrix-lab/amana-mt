"""Regression test for the MetricX-24 EOS/padding bug (fixed 2026-11-05).

A segment's score must not depend on what it is batched with. The buggy version
padded the batch and then dropped the last column, so a short item batched with
a longer one kept its EOS token and got a different score than when scored alone.

Needs the MetricX checkpoint and the google/mt5-large tokenizer (HF cache);
skipped otherwise. Run on a GPU node:
    .venv/bin/python -m pytest tests/test_metricx_batch_invariance.py -q
"""
import pytest

torch = pytest.importorskip("torch")

SHORT = ("Das Haus ist klein.", "The house is small.", "The house is small.")
LONG = (
    "Die Regierung kündigte am Montag ein umfassendes Paket von Maßnahmen an, "
    "das die Inflation bremsen und gleichzeitig Haushalte mit niedrigem Einkommen entlasten soll.",
    "On Monday the government announced a comprehensive package of measures intended to curb "
    "inflation while relieving low-income households.",
    "On Monday, the government unveiled a broad set of measures meant to slow inflation and "
    "at the same time ease the burden on low-income households.",
)


@pytest.fixture(scope="module")
def metricx():
    try:
        from mqmbench.metrics import metricx as m
        m._load("google/metricx-24-hybrid-large-v2p6-bfloat16")
    except Exception as exc:  # model or tokenizer not cached
        pytest.skip(f"MetricX checkpoint unavailable: {exc}")
    return m


def test_score_independent_of_batch_partner(metricx):
    alone = metricx.score([SHORT[0]], [SHORT[1]], [SHORT[2]], batch_size=1)[0]
    batched = metricx.score([SHORT[0], LONG[0]], [SHORT[1], LONG[1]], [SHORT[2], LONG[2]],
                            batch_size=2)[0]
    # bf16 padded attention can differ by tiny amounts; the bug produced >1 point gaps
    assert abs(alone - batched) < 0.05, (alone, batched)


def test_longest_item_unchanged(metricx):
    alone = metricx.score([LONG[0]], [LONG[1]], [LONG[2]], batch_size=1)[0]
    batched = metricx.score([SHORT[0], LONG[0]], [SHORT[1], LONG[1]], [SHORT[2], LONG[2]],
                            batch_size=2)[1]
    assert abs(alone - batched) < 0.05, (alone, batched)
