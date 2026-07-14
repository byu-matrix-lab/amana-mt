"""Score de-en (German→English) from WMT DA — genuinely unseen pair.

de-en is the largest unseen direction in the WMT DA dataset (n=134,796).
In the current pipeline, German comes from WMT MQM (Tier 1a, en-de direction).
de-en (German source, English target) has never been scored.

Lookup table prediction: X→en fusional → CK23 (plurality, consistent with cs-en + lt-en).

Metrics scored here: COMET-22, CometKiwi-23, MetricX-24.
These are the three focal metrics for the lookup table validation.

Run via SLURM:
  sbatch scripts/slurm/run_score_de_en.sh
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mqmbench.data.wmt_da import load_wmt_da
from mqmbench.config import init_settings, settings

RESULTS = Path(__file__).resolve().parent.parent / "results"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = RESULTS / "scores_de_en.csv"


def score_with_model(model_name: str, sources: list, hyps: list, refs: list,
                     batch_size: int = 16, gpus: int = 1, reference_free: bool = False):
    """Score with a COMET-family model."""
    from comet import download_model, load_from_checkpoint
    model_path = download_model(model_name)
    model = load_from_checkpoint(model_path)
    if reference_free:
        data = [{"src": str(s), "mt": str(h)} for s, h in zip(sources, hyps)]
    else:
        data = [{"src": str(s), "mt": str(h), "ref": str(r)} for s, h, r in zip(sources, hyps, refs)]
    output = model.predict(data, batch_size=batch_size, gpus=gpus)
    return output.scores


def score_metricx(sources: list, hyps: list, refs: list, batch_size: int = 8):
    """Score with MetricX-24."""
    try:
        from mqmbench.metrics.metricx import score as mx_score
        return mx_score(sources, hyps, refs, batch_size=batch_size)
    except ImportError:
        print("MetricX wrapper not available, skipping.", file=sys.stderr)
        return [float("nan")] * len(sources)


def main():
    init_settings(str(PROJECT_ROOT / "settings.toml"))

    print("Loading de-en WMT DA data...", flush=True)
    da = load_wmt_da(target_langs=["de"])
    da_de_en = da[da["segment_id"].str.startswith("de-en")].copy().reset_index(drop=True)
    print(f"  de-en rows (raw): {len(da_de_en)}", flush=True)

    # Drop rows with null source or hypothesis — tokenizer crashes on None/NaN
    before = len(da_de_en)
    da_de_en = da_de_en.dropna(subset=["source", "hypothesis"]).reset_index(drop=True)
    dropped = before - len(da_de_en)
    if dropped:
        print(f"  Dropped {dropped} rows with null source/hypothesis", flush=True)
    print(f"  de-en rows (clean): {len(da_de_en)}", flush=True)

    if da_de_en.empty:
        print("ERROR: No de-en data found.", file=sys.stderr)
        sys.exit(1)

    sources = da_de_en["source"].tolist()
    hyps    = da_de_en["hypothesis"].tolist()
    refs    = da_de_en.get("reference", pd.Series([""] * len(da_de_en))).fillna("").tolist()

    # Load existing partial results if any, to skip already-scored models
    if OUT_PATH.exists():
        result_df = pd.read_csv(OUT_PATH)
        print(f"  Loaded existing results ({len(result_df)} rows, cols: {list(result_df.columns)})", flush=True)
        # Align to cleaned da_de_en
        if len(result_df) != len(da_de_en):
            print("  Row count mismatch — starting fresh", flush=True)
            result_df = da_de_en[["segment_id", "quality_score"]].copy()
    else:
        result_df = da_de_en[["segment_id", "quality_score"]].copy()

    batch_size = getattr(settings.metrics.comet, "batch_size", 16)

    # ------------------------------------------------------------------ #
    # COMET-22 (reference-based)                                           #
    # ------------------------------------------------------------------ #
    if "comet" not in result_df.columns:
        print("Scoring with COMET-22 (wmt22-comet-da)...", flush=True)
        comet_scores = score_with_model(
            "Unbabel/wmt22-comet-da", sources, hyps, refs, batch_size=batch_size,
        )
        result_df["comet"] = comet_scores
        result_df.to_csv(OUT_PATH, index=False)
        print(f"  COMET-22 done. Mean={np.mean(comet_scores):.3f}", flush=True)
    else:
        print("  COMET-22 already scored, skipping.", flush=True)

    # ------------------------------------------------------------------ #
    # CometKiwi-23 (reference-free)                                        #
    # ------------------------------------------------------------------ #
    if "cometkiwi23" not in result_df.columns:
        print("Scoring with CometKiwi-23 (wmt23-cometkiwi-da-xl)...", flush=True)
        ck23_scores = score_with_model(
            "Unbabel/wmt23-cometkiwi-da-xl", sources, hyps, refs,
            batch_size=batch_size, reference_free=True,
        )
        result_df["cometkiwi23"] = ck23_scores
        result_df.to_csv(OUT_PATH, index=False)
        print(f"  CK23 done. Mean={np.mean(ck23_scores):.3f}", flush=True)
    else:
        print("  CK23 already scored, skipping.", flush=True)

    # ------------------------------------------------------------------ #
    # MetricX-24                                                           #
    # ------------------------------------------------------------------ #
    if "metricx" not in result_df.columns:
        print("Scoring with MetricX-24...", flush=True)
        mx_scores = score_metricx(sources, hyps, refs,
                                  batch_size=getattr(settings.metrics, "metricx_batch_size", 8))
        result_df["metricx"] = mx_scores
        result_df.to_csv(OUT_PATH, index=False)
        print(f"  MetricX done. Mean={np.nanmean(mx_scores):.3f}", flush=True)
    else:
        print("  MetricX already scored, skipping.", flush=True)

    # ------------------------------------------------------------------ #
    # Final report                                                          #
    # ------------------------------------------------------------------ #
    result_df = pd.read_csv(OUT_PATH)
    print(f"\nSaved: results/scores_de_en.csv ({len(result_df):,} rows)", flush=True)

    print("\n" + "=" * 60)
    print("de-en Lookup Table Validation (X→en fusional)")
    print("=" * 60)
    human = result_df["quality_score"].values
    rhos = {}
    for metric in ["comet", "cometkiwi23", "metricx"]:
        if metric not in result_df.columns:
            continue
        m = result_df[metric].values
        valid = ~(np.isnan(human) | np.isnan(m))
        rho, _ = spearmanr(human[valid], m[valid])
        rhos[metric] = rho
        print(f"  {metric:15s}: ρ={rho:.3f}  n={valid.sum():,}")

    print("\nLookup table prediction for X→en fusional: CK23")
    if "cometkiwi23" in rhos and "comet" in rhos:
        winner = "CK23 ✓" if rhos["cometkiwi23"] > rhos["comet"] else "COMET wins (unexpected)"
        print(f"  CK23 ρ={rhos.get('cometkiwi23', float('nan')):.3f} vs COMET ρ={rhos.get('comet', float('nan')):.3f} → {winner}")


if __name__ == "__main__":
    main()
