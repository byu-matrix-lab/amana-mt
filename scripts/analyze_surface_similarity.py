"""Surface similarity analysis: do correct translations look like their references?

For each language (he, de, zh) from WMT23:
  1. Compute per-segment MQM quality score from span annotations.
  2. Compute chrF(hypothesis, reference) for each segment.
  3. Show that high-quality Hebrew translations have LOW chrF with the reference,
     while high-quality German/Chinese translations have HIGH chrF.

This is the mechanistic evidence for the Reference Coverage Collapse hypothesis:
non-concatenative morphology causes correct translations to be surface-dissimilar
from the reference, blinding reference-based metrics to correct translations.

Output:
  results/surface_similarity.csv  — per (lang, system, seg) with mqm + chrF
  results/plots/presentation_surface_similarity.png
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

SPAN_BASE = Path("../wmt-mqm-human-evaluation")
SACREBLEU_CACHE = Path.home() / ".sacrebleu"

SEVERITY_PENALTY = {"major": 5.0, "minor": 1.0, "critical": 25.0}

# WMT23 configs: (lang, span_subdir, lang_pair, ref_line_offset)
# ref_line_offset: 0 = globalSegId IS the 0-indexed line; 1 = globalSegId is 1-indexed
LANGS = [
    ("he", "generalMT2023/heen", "he-en", 0),
    ("de", "generalMT2023/ende", "en-de", 1),
    ("zh", "generalMT2023/zhen", "zh-en", 1),
]

SCRIPT_TYPE = {"he": "abjad", "de": "alphabetic", "zh": "logographic"}
LANG_LABEL = {"he": "Hebrew (abjad)", "de": "German (alphabetic)", "zh": "Chinese (logographic)"}


def load_src_ref_lookup(lang_pair: str) -> dict[str, str]:
    """Build {source_text: reference_text} using sacreBLEU source and ref files.

    Aligns by source text position, which is robust to globalSegId ordering
    differences between the WMT MQM span TSVs and the sacreBLEU file ordering.
    """
    base = SACREBLEU_CACHE / "wmt23"
    src_path = base / f"wmt23.{lang_pair}.src"
    ref_path = base / f"wmt23.{lang_pair}.ref-refA"
    if not src_path.exists() or not ref_path.exists():
        print(f"  WARNING: src/ref files not found for {lang_pair}")
        return {}
    srcs = src_path.read_text(encoding="utf-8").splitlines()
    refs = ref_path.read_text(encoding="utf-8").splitlines()
    lookup = {}
    for src, ref in zip(srcs, refs):
        lookup[src.strip()] = ref.strip()
    return lookup


def compute_chrf(hyp: str, ref: str) -> float:
    """Character n-gram F-score (chrF, β=2, n=6)."""
    if not hyp or not ref:
        return 0.0
    n = 6
    def char_ngrams(s, n):
        return [s[i:i+n] for i in range(len(s) - n + 1)]

    scores = []
    for k in range(1, n + 1):
        hyp_ng = char_ngrams(hyp, k)
        ref_ng = char_ngrams(ref, k)
        if not hyp_ng or not ref_ng:
            continue
        hyp_counts = {}
        for g in hyp_ng:
            hyp_counts[g] = hyp_counts.get(g, 0) + 1
        ref_counts = {}
        for g in ref_ng:
            ref_counts[g] = ref_counts.get(g, 0) + 1
        matches = sum(min(hyp_counts.get(g, 0), ref_counts.get(g, 0))
                      for g in ref_counts)
        prec = matches / len(hyp_ng)
        rec  = matches / len(ref_ng)
        if prec + rec > 0:
            beta = 2.0
            f = (1 + beta**2) * prec * rec / (beta**2 * prec + rec)
            scores.append(f)
    return float(np.mean(scores)) if scores else 0.0


def load_lang(lang: str, subdir: str, lang_pair: str, offset: int):
    tsv_name = f"mqm_{subdir.replace('/', '_')}_{lang_pair.replace('-','')}.tsv"
    tsv_path = SPAN_BASE / subdir / tsv_name
    if not tsv_path.exists():
        candidates = list((SPAN_BASE / subdir).glob("*.tsv"))
        if candidates:
            tsv_path = candidates[0]
        else:
            print(f"  No TSV found for {lang} in {subdir}")
            return pd.DataFrame()

    df = pd.read_csv(tsv_path, sep="\t", on_bad_lines="skip")
    print(f"  {lang}: {len(df)} span rows from {tsv_path.name}")

    # For he-en: offset-based lookup works (established empirically).
    # For en-de / zh-en: use source-text matching — sacreBLEU file ordering
    # does not correspond to globalSegId ordering.
    if lang == "he":
        ref_path = SACREBLEU_CACHE / "wmt23" / f"wmt23.{lang_pair}.ref-refA"
        lines = ref_path.read_text(encoding="utf-8").splitlines()
        refs_by_segid = {i + offset: line for i, line in enumerate(lines)}
    else:
        refs_by_segid = None

    src_ref_lookup = load_src_ref_lookup(lang_pair) if lang != "he" else {}

    # Compute penalty per row
    def row_penalty(row):
        sev = str(row.get("severity", "")).lower()
        cat = str(row.get("category", "")).lower()
        if sev in ("ok", "no-error", "") or cat in ("no-error", ""):
            return 0.0
        return SEVERITY_PENALTY.get(sev, 0.0)

    df["penalty"] = df.apply(row_penalty, axis=1)

    seg_col = "globalSegId" if "globalSegId" in df.columns else "seg_id"
    hyp_col = "target"
    sys_col = "system"

    agg = (
        df.groupby([sys_col, seg_col])
        .agg(
            source=("source", "first"),
            hypothesis=(hyp_col, "first"),
            total_penalty=("penalty", "sum"),
            n_raters=("penalty", "count"),
        )
        .reset_index()
    )
    agg["mqm_score"] = -(agg["total_penalty"] / agg["n_raters"].clip(lower=1))

    if refs_by_segid is not None:
        agg["reference"] = agg[seg_col].map(refs_by_segid)
    else:
        agg["reference"] = agg["source"].map(src_ref_lookup)

    agg = agg.dropna(subset=["reference"])
    n_ref = len(agg)
    print(f"  {lang}: {n_ref} segments with matched references")

    agg["chrf"] = [
        compute_chrf(h, r)
        for h, r in zip(agg["hypothesis"], agg["reference"])
    ]
    agg["lang"] = lang
    agg["script_type"] = SCRIPT_TYPE[lang]
    return agg[[sys_col, seg_col, "lang", "script_type", "mqm_score", "chrf",
                "hypothesis", "reference"]]


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    all_dfs = []
    for lang, subdir, lp, offset in LANGS:
        print(f"Loading {lang}...")
        df = load_lang(lang, subdir, lp, offset)
        if not df.empty:
            all_dfs.append(df)
            print(f"  {lang}: {len(df)} segments, "
                  f"mean mqm={df['mqm_score'].mean():.2f}, "
                  f"mean chrF={df['chrf'].mean():.3f}")

    if not all_dfs:
        print("No data loaded.")
        return

    combined = pd.concat(all_dfs, ignore_index=True)
    out_dir = Path("results")
    combined.to_csv(out_dir / "surface_similarity.csv", index=False)
    print(f"\nSaved results/surface_similarity.csv ({len(combined)} rows)")

    # ── Summary table by quality bucket ──────────────────────────────────────
    combined["quality_bucket"] = pd.cut(
        combined["mqm_score"],
        bins=[-999, -10, -3, -1, 0.001],
        labels=["poor (< -10)", "medium (-10 to -3)", "good (-3 to -1)", "perfect (0)"],
    )
    table = (
        combined.groupby(["lang", "quality_bucket"], observed=True)["chrf"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "mean_chrF", "count": "n"})
    )
    print("\n── Mean chrF by language and MQM quality bucket ──")
    print(table.to_string())

    # ── Figure: scatter with regression lines ─────────────────────────────────
    plt.rcParams.update({
        "font.size": 13, "axes.titlesize": 14, "axes.labelsize": 13,
        "xtick.labelsize": 11, "ytick.labelsize": 11,
        "figure.dpi": 150, "axes.spines.top": False, "axes.spines.right": False,
    })

    COLORS = {"he": "#d6604d", "de": "#2166ac", "zh": "#4dac26"}
    MARKERS = {"he": "o", "de": "s", "zh": "^"}

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    # Left: scatter mqm_score vs chrf, all segments
    ax = axes[0]
    for lang in ["de", "zh", "he"]:
        sub = combined[combined["lang"] == lang].sample(
            min(800, len(combined[combined["lang"] == lang])), random_state=42)
        ax.scatter(sub["mqm_score"], sub["chrf"],
                   color=COLORS[lang], marker=MARKERS[lang],
                   alpha=0.35, s=20, label=LANG_LABEL[lang], zorder=2)
        # Regression line
        x = sub["mqm_score"].values
        y = sub["chrf"].values
        mask = np.isfinite(x) & np.isfinite(y)
        if mask.sum() > 2:
            m, b = np.polyfit(x[mask], y[mask], 1)
            xs = np.linspace(x[mask].min(), x[mask].max(), 100)
            ax.plot(xs, m * xs + b, color=COLORS[lang], linewidth=2.0)

    ax.set_xlabel("MQM quality score (0 = perfect, more negative = worse)")
    ax.set_ylabel("chrF with reference translation")
    ax.set_title("Surface Similarity vs. Translation Quality\n(WMT23 MQM segments)")
    ax.legend(frameon=False, fontsize=11)
    ax.axvline(0, color="gray", linewidth=0.7, linestyle=":")

    # Right: boxplot of chrF for perfect segments (mqm_score == 0) only
    ax = axes[1]
    perfect = combined[combined["mqm_score"] == 0]
    lang_order = ["de", "zh", "he"]
    data_by_lang = [perfect[perfect["lang"] == l]["chrf"].values for l in lang_order]
    labels = [LANG_LABEL[l] for l in lang_order]
    colors = [COLORS[l] for l in lang_order]

    bp = ax.boxplot(data_by_lang, labels=labels, patch_artist=True,
                    medianprops=dict(color="black", linewidth=2))
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)

    ns = [len(d) for d in data_by_lang]
    for i, (n, d) in enumerate(zip(ns, data_by_lang), 1):
        ax.text(i, ax.get_ylim()[0] if ax.get_ylim()[0] > 0 else 0.02,
                f"n={n}", ha="center", va="bottom", fontsize=9, color="#555")

    ax.set_ylabel("chrF with reference translation")
    ax.set_title("chrF for Error-Free Translations\n(MQM penalty = 0)")
    ax.set_ylim(0, 1.0)

    # Annotation: Hebrew gap
    he_med = np.median(data_by_lang[2]) if len(data_by_lang[2]) > 0 else 0
    de_med = np.median(data_by_lang[0]) if len(data_by_lang[0]) > 0 else 0
    if he_med > 0 and de_med > 0:
        gap = de_med - he_med
        ax.annotate(
            f"Gap: {gap:+.2f}\n(DE−HE median)",
            xy=(2.5, (he_med + de_med) / 2),
            xytext=(2.2, (he_med + de_med) / 2 + 0.05),
            fontsize=9, color="#c0392b",
            arrowprops=dict(arrowstyle="-", color="#c0392b", lw=1.0),
        )

    fig.suptitle(
        "Reference Coverage Collapse: Correct Hebrew Translations\n"
        "Are Surface-Dissimilar from Their References",
        fontsize=14, y=1.02,
    )
    plt.tight_layout()

    plot_path = Path("results/plots/presentation_surface_similarity.png")
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(plot_path, bbox_inches="tight")
    plt.close()
    print(f"Saved {plot_path}")


if __name__ == "__main__":
    main()
