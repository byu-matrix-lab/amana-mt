"""Shared loaders for the official mt-metrics-eval-v2 files (MQM control and follow-up analyses)."""
from pathlib import Path

import numpy as np
import pandas as pd

# metric file stems per edition (closest available analogues across years)
METRICS = {
    "wmt20": {"chrF": "chrF-ref", "sentBLEU": "sentBLEU-ref", "BLEURT": "BLEURT-extended-ref",
              "COMET": "COMET-ref", "COMET-QE": "COMET-QE-src"},
    "wmt21.news": {"chrF": "chrF-refA", "sentBLEU": "sentBLEU-refA", "BLEURT": "bleurt-20-refA",
                   "COMET": "COMET-DA_2021-refA", "COMET-QE": "COMET-QE-DA_2021-src"},
    "wmt22": {"chrF": "chrF-refA", "sentBLEU": "BLEU-refA", "BLEURT": "BLEURT-20-refA",
              "COMET": "COMET-22-refA", "COMET-QE": "COMETKiwi-src",
              "MetricX": "metricx_xxl_MQM_2020-refA"},
    "wmt23": {"chrF": "chrF-refA", "sentBLEU": "BLEU-refA", "BLEURT": "BLEURT-20-refA",
              "COMET": "COMET-refA", "COMET-QE": "CometKiwi-src", "MetricX": "MetricX-23-refA"},
}
# human label files per edition: name -> file infix
LABELS = {
    "wmt20": {"MQM": "mqm", "DA": "wmt-z"},
    "wmt21.news": {"MQM": "mqm", "DA": "wmt-z"},
    "wmt22": {"MQM": "mqm", "DA": "wmt-z", "DA-appraise": "wmt-appraise-z"},
    "wmt23": {"MQM": "mqm", "DA": "da-sqm"},  # WMT23: source-based DA+SQM in BOTH directions
}
PAIRS = {"wmt20": ["en-de", "zh-en"], "wmt21.news": ["en-de", "en-ru", "zh-en"],
         "wmt22": ["en-de", "en-ru", "zh-en"], "wmt23": ["en-de", "zh-en", "he-en"]}


def read_seg(path):
    """mt-metrics-eval seg file: '<system><ws><score>' per line, segments in order per system."""
    path = Path(path)
    if not path.exists():
        return None
    sysn, score = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        s, v = line.rsplit(None, 1)
        sysn.append(s)
        score.append(np.nan if v == "None" else float(v))
    df = pd.DataFrame({"system": sysn, "score": score})
    df["seg"] = df.groupby("system").cumcount()
    return df.set_index(["system", "seg"]).score


def da_protocol(tset, lp, has_crowd_da):
    if tset == "wmt23":
        return "source-based DA+SQM" if has_crowd_da else "none (MQM only)"
    if tset in ("wmt20", "wmt21.news"):
        return "crowd ref-based" if lp.endswith("-en") else "source-based (bilingual)"
    return "crowd ref-based" if has_crowd_da else "source-based appraise"


def primary_metric_stems(mtme, tset, lp):
    """Every submitted metric's primary variant (refA/ref or src), excluding refB, -all and synthetic refs."""
    d = Path(mtme) / tset / "metric-scores" / lp
    stems = [f.name[:-len(".seg.score")] for f in d.glob("*.seg.score")]
    keep = [s for s in stems if s.endswith(("-refA", "-ref", "-src"))]
    return sorted(keep)


def load_pair(mtme, tset, lp, all_metrics=False):
    """DataFrame indexed by (system, seg): human label columns + metric columns, and the DA protocol.

    WMT22 en->X has only source-based Appraise DA (no crowd DA); it is used as "DA" there.
    """
    mtme = Path(mtme)
    cols = {}
    for lab, infix in LABELS[tset].items():
        s = read_seg(mtme / tset / "human-scores" / f"{lp}.{infix}.seg.score")
        if s is not None:
            cols[lab] = s
    proto = da_protocol(tset, lp, "DA" in cols)
    if "DA" not in cols and "DA-appraise" in cols:
        cols["DA"] = cols.pop("DA-appraise")
    stems = ({s: s for s in primary_metric_stems(mtme, tset, lp)} if all_metrics
             else METRICS[tset])
    for m, stem in stems.items():
        s = read_seg(mtme / tset / "metric-scores" / lp / f"{stem}.seg.score")
        if s is not None:
            cols[m] = s
    return pd.DataFrame(cols), proto
