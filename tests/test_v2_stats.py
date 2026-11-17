"""Tests for the statistics fixed for the corrected paper (2026-11-09/10).

1. williams_test matches the mt-metrics-eval implementation (Graham & Baldwin
   2014), and holds its size under the null (Eric Ringger's audit, item 5).
2. The grouped bootstrap resamples whole groups and widens the interval when
   rows within a group are dependent.
3. correlate_metric_vs_human drops NaN pairs jointly.
4. metric_scope: GEMBA excluded, BLEURT English-target only.

    .venv/bin/python -m pytest tests/test_v2_stats.py -q
"""
import numpy as np
import pandas as pd
import scipy.stats
from scipy.stats import spearmanr

from mqmbench.analysis.correlation import _bootstrap_ci, correlate_metric_vs_human, williams_test
from mqmbench.analysis.metric_scope import apply_metric_scope, in_scope, target_language


# Copied verbatim from google-research/mt-metrics-eval, mt_metrics_eval/stats.py
# (commit 68a481aea1a787392d55af8f76ac8ef40c5f4664, 2026-04-23).
# Copyright 2021 Google LLC. Licensed under the Apache License, Version 2.0.
def _mtme_williams_test(r12, r13, r23, n, one_sided=True):
    """Return Williams test p-value for given Pearson correlations."""
    k = 1 - r12**2 - r13**2 - r23**2 + 2 * r12 * r23 * r13
    rbar = ((r12 + r13) / 2)
    tnum = (r12 - r13) * np.sqrt((n - 1) * (1 + r23))
    tden = np.sqrt(2 * (n - 1) / (n - 3) * k + rbar**2 * (1 - r23)**3)
    p = scipy.stats.t.sf(np.abs(tnum / tden), n - 3)
    return p if one_sided else 2 * p


def _draw(n, rng, gap=0.0):
    h = rng.normal(size=n)
    m1 = h + rng.normal(scale=1.0, size=n)
    m2 = h + rng.normal(scale=1.0 + gap, size=n)
    return h, m1, m2


def test_williams_matches_mt_metrics_eval():
    rng = np.random.default_rng(0)
    for n, gap in [(50, 0.0), (500, 0.3), (5000, 0.05)]:
        h, m1, m2 = _draw(n, rng, gap)
        _, p = williams_test(h, m1, m2)
        r1 = spearmanr(m1, h)[0]
        r2 = spearmanr(m2, h)[0]
        r12 = spearmanr(m1, m2)[0]
        p_ref = _mtme_williams_test(r1, r2, r12, n, one_sided=False)
        assert np.isclose(p, p_ref, rtol=1e-10, atol=1e-14), (n, p, p_ref)


def test_williams_size_under_null():
    rng = np.random.default_rng(1)
    pvals = [williams_test(*_draw(500, rng))[1] for _ in range(400)]
    rate = np.mean(np.array(pvals) < 0.05)
    assert 0.02 <= rate <= 0.09, rate  # nominal 0.05; the pre-fix formula gave ~0.9


def test_grouped_bootstrap_resamples_whole_groups_and_widens():
    rng = np.random.default_rng(2)
    # 40 source sentences x 25 systems; human and metric share a per-source effect.
    src = np.repeat(np.arange(40), 25)
    effect = rng.normal(size=40)[src]
    h = effect + rng.normal(scale=0.5, size=src.size)
    m = effect + rng.normal(scale=0.5, size=src.size)
    stat = lambda x, y: spearmanr(x, y)[0]
    lo_i, hi_i = _bootstrap_ci(h, m, stat, n_boot=300)
    lo_g, hi_g = _bootstrap_ci(h, m, stat, n_boot=300, groups=src)
    assert hi_g - lo_g > 1.5 * (hi_i - lo_i)


def test_correlate_drops_nan_pairs_jointly():
    h = [1.0, 2.0, 3.0, 4.0, 5.0, np.nan]
    m = [1.0, 2.0, np.nan, 4.0, 5.0, 6.0]
    r = correlate_metric_vs_human(h, m, "x", "xx", n_boot=50, groups=list("aabbcc"))
    assert r["n"] == 4
    assert np.isclose(r["spearman_r"], 1.0)


def test_metric_scope():
    ids = pd.Series(["en-de_2020_news_0", "zh-en_2021_news_3", "he_sysA_12", "es_sysB_4",
                     "flores_devtest_0001", "de-fr_2022_x_1", "cs-en_2019_y"])
    assert target_language(ids).fillna("-").tolist() == ["de", "en", "en", "es", "-", "fr", "en"]
    # 2026-11-16: BLEURT and GEMBA are excluded outright.
    assert not in_scope("bleurt", ids).any()
    assert not in_scope("gemba", ids).any()
    assert in_scope("comet", ids).all()
    df = pd.DataFrame({"segment_id": ids, "bleurt": 1.0})
    assert apply_metric_scope(df, "bleurt").bleurt.isna().all()
