"""Follow-up analyses on the MQM-vs-DA control (official mt-metrics-eval-v2 files only).

A. Ranking flips: on the same segments, does ranking ALL submitted metrics by
   correlation with crowd/source DA give the same order as ranking by MQM?
B. Grouping robustness: pooled vs item-grouped (per segment, across systems)
   vs system-level correlation, for the core metrics under each label.
C. Bootstrap CIs (resampling source segments) for COMET~MQM, COMET~DA,
   MQM~DA per pair-year, and the same-year en->X minus X->en gap per label.
D. Human-agreement ceiling: MQM inter-rater reliability (WMT20, 3 ratings per
   segment) and DA test-retest reliability (from audit_da_label_quality.csv),
   turned into a max-attainable correlation sqrt(reliability).

Usage: python followup_analyses.py <path to mt-metrics-eval-v2>
"""
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, pearsonr, rankdata, spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mtme_io import METRICS, PAIRS, load_pair, read_seg  # noqa: E402

MTME = Path(sys.argv[1])
ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results"
N_BOOT = 1000
SURFACE = ("BLEU", "chrF", "sentBLEU", "TER", "f101spBLEU", "f200spBLEU", "CharacTER", "EED")
rng = np.random.default_rng(0)
pd.set_option("display.width", 250)


def direction(lp):
    return "x_to_en" if lp.endswith("-en") else "en_to_x"


def fast_spearman(a, b):
    ra, rb = rankdata(a), rankdata(b)
    return np.corrcoef(ra, rb)[0, 1]


# ---------------------------------------------------------------- A. ranking flips
rank_rows, long_rows = [], []
for tset, lps in PAIRS.items():
    for lp in lps:
        df, proto = load_pair(MTME, tset, lp, all_metrics=True)
        if "DA" not in df:
            continue
        core = df.dropna(subset=["MQM", "DA"])
        mcols = [c for c in core.columns if c not in ("MQM", "DA", "DA-appraise")]
        # human-reference "systems" can't be scored by metrics that use that reference:
        # drop systems most metrics skip, THEN keep metrics with near-full coverage
        sys_cov = core[mcols].notna().groupby(level="system").mean().mean(axis=1)
        core = core[core.index.get_level_values("system").isin(sys_cov[sys_cov >= 0.5].index)]
        mcols = [c for c in mcols if core[c].notna().mean() >= 0.95]
        core = core.dropna(subset=mcols)
        cm = {m: spearmanr(core[m], core.MQM).correlation for m in mcols}
        cd = {m: spearmanr(core[m], core.DA).correlation for m in mcols}
        for m in mcols:
            long_rows.append(dict(testset=tset, lp=lp, da_protocol=proto, metric=m,
                                  rho_MQM=cm[m], rho_DA=cd[m]))
        order_m = sorted(mcols, key=lambda m: -cm[m])
        order_d = sorted(mcols, key=lambda m: -cd[m])
        surf = [m for m in mcols if m.startswith(SURFACE)]
        rank_rows.append(dict(
            testset=tset, lp=lp, direction=direction(lp), da_protocol=proto, n=len(core),
            n_metrics=len(mcols), n_systems=core.index.get_level_values("system").nunique(),
            n_surface=len([m for m in mcols if m.startswith(SURFACE)]),
            tau_rankings=kendalltau([cm[m] for m in mcols], [cd[m] for m in mcols]).correlation,
            top1_MQM=order_m[0], top1_DA=order_d[0], top1_same=order_m[0] == order_d[0],
            top3_overlap=len(set(order_m[:3]) & set(order_d[:3])),
            # where do surface metrics land? (rank 1 = best)
            best_surface_rank_MQM=min(order_m.index(m) for m in surf) + 1 if surf else np.nan,
            best_surface_rank_DA=min(order_d.index(m) for m in surf) + 1 if surf else np.nan))
rank = pd.DataFrame(rank_rows)
rank.to_csv(RES / "followup_ranking_flips.csv", index=False)
pd.DataFrame(long_rows).to_csv(RES / "followup_metric_corrs_all.csv", index=False)
print("=== A. Ranking flips: all submitted metrics ranked by rho with MQM vs with DA (same segments)")
print(rank.round(3).to_string(index=False))

# ---------------------------------------------------------------- B. grouping robustness
grp_rows = []
for tset, lps in PAIRS.items():
    for lp in lps:
        df, proto = load_pair(MTME, tset, lp)
        labels = ["MQM", "DA"] if "DA" in df else ["MQM"]
        metrics = [m for m in METRICS[tset] if m in df]
        core = df.dropna(subset=labels + metrics)
        segs = core.index.get_level_values("seg")
        sysm = core.groupby(level="system").mean()
        for lab in labels:
            for m in metrics:
                item = []
                for _, g in core.groupby(segs):
                    if len(g) >= 3 and g[lab].nunique() > 1 and g[m].nunique() > 1:
                        item.append(spearmanr(g[m], g[lab]).correlation)
                grp_rows.append(dict(
                    testset=tset, lp=lp, direction=direction(lp), da_protocol=proto, label=lab, metric=m,
                    pooled=spearmanr(core[m], core[lab]).correlation,
                    item_grouped=np.nanmean(item) if item else np.nan, n_items=len(item),
                    system_pearson=pearsonr(sysm[m], sysm[lab])[0],
                    system_spearman=spearmanr(sysm[m], sysm[lab]).correlation,
                    n_systems=len(sysm)))
grp = pd.DataFrame(grp_rows)
grp.to_csv(RES / "followup_grouping.csv", index=False)
print("\n=== B. Grouping robustness (COMET and chrF)")
show = grp[grp.metric.isin(["COMET", "chrF"])]
print(show[["testset", "lp", "da_protocol", "label", "metric", "pooled", "item_grouped",
            "system_pearson", "n_systems"]].round(3).to_string(index=False))

# ---------------------------------------------------------------- C. bootstrap CIs
boot_data = {}
for tset, lps in PAIRS.items():
    for lp in lps:
        df, proto = load_pair(MTME, tset, lp)
        labels = ["MQM", "DA"] if "DA" in df else ["MQM"]
        core = df.dropna(subset=labels + ["COMET"]).reset_index()
        boot_data[(tset, lp)] = (core, labels, proto)


def stats_for(core, labels):
    out = {"COMET~MQM": fast_spearman(core.COMET.values, core.MQM.values)}
    if "DA" in labels:
        out["COMET~DA"] = fast_spearman(core.COMET.values, core.DA.values)
        out["MQM~DA"] = fast_spearman(core.MQM.values, core.DA.values)
    return out


point = {k: stats_for(c, l) for k, (c, l, _) in boot_data.items()}
reps = {k: [] for k in boot_data}
seg_index = {k: c.groupby("seg").indices for k, (c, _, _) in boot_data.items()}
for _ in range(N_BOOT):
    for k, (core, labels, _) in boot_data.items():
        idx = seg_index[k]
        keys = list(idx)
        pick = rng.choice(len(keys), size=len(keys), replace=True)
        rows_ = np.concatenate([idx[keys[i]] for i in pick])
        reps[k].append(stats_for(core.iloc[rows_], labels))

ci_rows = []
for k, (core, labels, proto) in boot_data.items():
    r = pd.DataFrame(reps[k])
    for stat in r.columns:
        ci_rows.append(dict(testset=k[0], lp=k[1], direction=direction(k[1]), da_protocol=proto,
                            stat=stat, point=point[k][stat],
                            lo=r[stat].quantile(0.025), hi=r[stat].quantile(0.975)))
# same-year direction gap (mean en->X minus mean X->en), per label, resampled jointly
for tset in PAIRS:
    keys = [k for k in boot_data if k[0] == tset]
    for stat in ["COMET~MQM", "COMET~DA"]:
        ks = [k for k in keys if stat in point[k]]
        e = [k for k in ks if direction(k[1]) == "en_to_x"]
        x = [k for k in ks if direction(k[1]) == "x_to_en"]
        if not e or not x:
            continue
        gap = lambda get: np.mean([get(k) for k in e]) - np.mean([get(k) for k in x])
        pt = gap(lambda k: point[k][stat])
        g = [gap(lambda k: reps[k][b][stat]) for b in range(N_BOOT)]
        ci_rows.append(dict(testset=tset, lp="en->X minus X->en", direction="gap", da_protocol="",
                            stat=stat, point=pt, lo=np.quantile(g, 0.025), hi=np.quantile(g, 0.975)))
ci = pd.DataFrame(ci_rows)
ci.to_csv(RES / "followup_bootstrap_ci.csv", index=False)
print(f"\n=== C. Bootstrap 95% CIs ({N_BOOT} resamples of source segments)")
print(ci.round(3).to_string(index=False))

# ---------------------------------------------------------------- D. human-agreement ceiling
ceil_rows = []
for lp in ["en-de", "zh-en"]:
    cols = {f"col{i}": read_seg(MTME / "wmt20" / "human-scores" / f"{lp}.mqm-col{i}.seg.score")
            for i in (1, 2, 3)}
    c = pd.DataFrame(cols).dropna()
    r1 = np.mean([spearmanr(c[a], c[b]).correlation for a, b in combinations(c.columns, 2)])
    r3 = 3 * r1 / (1 + 2 * r1)  # Spearman-Brown: reliability of the 3-rating mean
    ceil_rows.append(dict(label="MQM", testset="wmt20", lp=lp, direction=direction(lp),
                          single_rater_reliability=r1, n_ratings=3, label_reliability=r3,
                          ceiling=np.sqrt(r3), n=len(c)))
# retest pairs are only independent ratings where WMT did NOT copy one rating to
# every system with an identical output (followup_da_retest_check.csv: exact-equal raw)
da_q = pd.read_csv(RES / "audit_da_label_quality.csv").merge(
    pd.read_csv(RES / "followup_da_retest_check.csv")[["year", "direction", "frac_raw_exactly_equal"]],
    on=["year", "direction"])
da_q = da_q[(da_q.frac_raw_exactly_equal < 0.15) & (da_q.n_retest_pairs >= 200)]
for _, r in da_q.dropna(subset=["retest_rho"]).iterrows():
    rel = max(r.retest_rho, 0)
    ceil_rows.append(dict(label="DA", testset=str(int(r.year)), lp="all", direction=r.direction,
                          single_rater_reliability=r.retest_rho, n_ratings=1, label_reliability=rel,
                          ceiling=np.sqrt(rel), n=int(r.n_retest_pairs)))
ceil = pd.DataFrame(ceil_rows)
ceil.to_csv(RES / "followup_ceiling.csv", index=False)
print("\n=== D. Human-agreement ceiling (max attainable correlation = sqrt(label reliability))")
print(ceil.round(3).to_string(index=False))
