"""
Metric reliability predictor: given typological features of a language, predict
how much a metric outperforms BLEU (spearman_r(metric) − spearman_r(BLEU)).

Target variable rationale: predicting absolute Spearman r learns "MetricX is
generally best" rather than when typology changes that ranking. The BLEU-relative
advantage captures "when does typology make metric choice matter?"

Design:
  - One Ridge regression per metric (8 models total)
  - Each model: 24 data points × ~8 typological features — sensible ratio,
    avoids over-regularization from metric one-hot + interaction terms
  - Target: spearman_r(metric) − spearman_r(BLEU) per language
  - Features: typological (WALS + manual) + morphology type + resource tier +
    translation direction (no metric identity — each model IS the interaction)
  - Evaluation: leave-one-language-out cross-validation (LOLO-CV) per model
  - Output: cv_predictions.csv, coefficients.csv, recommendation_table.csv
"""

import csv
import os
import json
import numpy as np
from collections import defaultdict

# ── Lookups from correlation.py ────────────────────────────────────────────────
MORPHOLOGY_TYPES = {
    "isolating":     ["zh", "th", "lo", "km", "my"],
    "agglutinative": ["tr", "fi", "et", "ka", "kk", "sw", "am", "ja", "ta"],
    "fusional":      ["de", "ru", "cs", "fr", "pl", "uk", "is", "lt", "lv",
                      "ps", "bn", "hi", "gu", "xh", "zu", "ha", "ht",
                      "es", "he"],
}
LANG_TO_MORPH = {lang: mt for mt, langs in MORPHOLOGY_TYPES.items() for lang in langs}

TRANSLATION_DIRECTIONS = {
    "x_to_en": ["zh", "uk", "km", "ps", "gu", "kk", "he"],
    "pivot":   ["fr", "bn", "hi", "xh", "zu"],
    "en_to_x": ["de", "ru", "cs", "tr", "pl", "fi", "et", "is",
                 "lt", "lv", "ta", "ja", "ha", "sw", "ht", "lo",
                 "th", "my", "am", "ka", "es"],
}
LANG_TO_DIR = {lang: d for d, langs in TRANSLATION_DIRECTIONS.items() for lang in langs}

# Exclude ensemble (derived), gemba (LLM judge), and bleu (it is the baseline)
EXCLUDE_METRICS = {"ensemble", "gemba", "bleu"}


def load_data(project_dir):
    dir_path = os.path.join(project_dir, "results", "direction_analysis.csv")
    typo_path = os.path.join(project_dir, "data", "typological_features.csv")

    typo = {}
    for r in csv.DictReader(open(typo_path)):
        typo[r["lang"]] = {
            "word_segmentation": int(r["word_segmentation"]),
            "word_order":        int(r["word_order"]) if r["word_order"] else None,
            "num_cases":         int(r["num_cases"]) if r["num_cases"] else None,
            "affix_direc":       int(r["affix_direc"]) if r["affix_direc"] else None,
        }

    # First pass: collect BLEU Spearman r per language (baseline)
    bleu_r = {}
    for r in csv.DictReader(open(dir_path)):
        if r["metric"] == "bleu" and r["spearman_r"]:
            bleu_r[r["lang"]] = float(r["spearman_r"])

    # Second pass: build rows with BLEU-relative target
    rows = []
    for r in csv.DictReader(open(dir_path)):
        if not r["spearman_r"] or r["metric"] in EXCLUDE_METRICS:
            continue
        lang = r["lang"]
        if lang not in typo or lang not in bleu_r:
            continue
        row = {
            "lang":            lang,
            "metric":          r["metric"],
            "spearman_r":      float(r["spearman_r"]),
            "bleu_r":          bleu_r[lang],
            "advantage":       float(r["spearman_r"]) - bleu_r[lang],  # target
            "resource_tier":   r["resource_tier"],
            "script_type":     r["script_type"],
            "morphology_type": LANG_TO_MORPH.get(lang, "fusional"),
            "direction":       LANG_TO_DIR.get(lang, "en_to_x"),
        }
        row.update(typo[lang])
        rows.append(row)
    return rows


def build_features(rows):
    """
    Build feature matrix X and target vector y for a single metric's rows.

    No metric identity features — each model is trained on one metric only,
    so the coefficients directly express how typology drives that metric's
    advantage over BLEU. Categorical features are one-hot with reference
    category dropped.
    """
    CAT_REFS = {
        "resource_tier":   "human_da",
        "script_type":     "alphabetic",
        "morphology_type": "fusional",
        "direction":       "en_to_x",
        "word_order":      2,   # SVO reference
    }
    TYPO_NUMERIC = ["word_segmentation", "num_cases", "affix_direc"]

    cat_vals = defaultdict(set)
    for r in rows:
        for col in ["resource_tier", "script_type", "morphology_type", "direction"]:
            cat_vals[col].add(r[col])
        if r["word_order"] is not None:
            cat_vals["word_order"].add(r["word_order"])

    dummies = {col: sorted(v for v in cat_vals[col] if v != ref)
               for col, ref in CAT_REFS.items()}

    feature_names = []
    X, y = [], []

    for r in rows:
        vec = []
        for col in ["resource_tier", "script_type", "morphology_type", "direction"]:
            for val in dummies[col]:
                vec.append(1.0 if r[col] == val else 0.0)
                if r is rows[0]:
                    feature_names.append(f"{col}={val}")

        for val in dummies["word_order"]:
            vec.append(1.0 if r["word_order"] == val else 0.0)
            if r is rows[0]:
                feature_names.append(f"word_order={val}")

        for col in TYPO_NUMERIC:
            v = float(r[col]) if r[col] is not None else 0.0
            vec.append(v)
            if r is rows[0]:
                feature_names.append(col)

        X.append(vec)
        y.append(r["advantage"])

    return np.array(X, dtype=float), np.array(y, dtype=float), feature_names


def ridge_fit_predict(X, y, alpha):
    """Closed-form ridge: (X'X + αI)^-1 X'y"""
    n, p = X.shape
    A = X.T @ X + alpha * np.eye(p)
    beta = np.linalg.solve(A, X.T @ y)
    return beta


def lolo_cv(rows, X, y, alpha):
    """Leave-one-language-out cross-validation."""
    langs = sorted(set(r["lang"] for r in rows))
    lang_idx = {lang: [i for i, r in enumerate(rows) if r["lang"] == lang] for lang in langs}

    preds = np.zeros(len(y))
    for lang in langs:
        test_idx = lang_idx[lang]
        train_idx = [i for i in range(len(y)) if i not in set(test_idx)]
        X_tr, y_tr = X[train_idx], y[train_idx]
        X_te = X[test_idx]
        beta = ridge_fit_predict(X_tr, y_tr, alpha)
        preds[test_idx] = X_te @ beta
    return preds


def tune_alpha(rows, X, y, alphas):
    """Pick alpha by LOLO-CV RMSE."""
    best_alpha, best_rmse = None, float("inf")
    for alpha in alphas:
        preds = lolo_cv(rows, X, y, alpha)
        rmse = np.sqrt(np.mean((preds - y) ** 2))
        if rmse < best_rmse:
            best_rmse = rmse
            best_alpha = alpha
    return best_alpha, best_rmse


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    out_dir = os.path.join(project_dir, "results", "predictor")
    os.makedirs(out_dir, exist_ok=True)

    print("Loading data...")
    all_rows = load_data(project_dir)
    metrics = sorted(set(r["metric"] for r in all_rows))
    langs_seen = sorted(set(r["lang"] for r in all_rows))
    print(f"  {len(all_rows)} pairs, {len(langs_seen)} languages, {len(metrics)} metrics")

    alphas = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]

    # ── Per-metric models ──────────────────────────────────────────────────────
    all_cv_rows = []
    coef_rows = []
    per_metric_summary = {}

    for metric in metrics:
        mrows = [r for r in all_rows if r["metric"] == metric]
        X, y, feat_names = build_features(mrows)

        col_mean = X.mean(axis=0)
        col_std  = X.std(axis=0)
        col_std[col_std == 0] = 1.0
        X_sc = (X - col_mean) / col_std

        best_alpha, best_rmse = tune_alpha(mrows, X_sc, y, alphas)
        cv_preds = lolo_cv(mrows, X_sc, y, best_alpha)
        cv_r = float(np.corrcoef(y, cv_preds)[0, 1]) if y.std() > 0 else 0.0
        beta = ridge_fit_predict(X_sc, y, best_alpha)

        per_metric_summary[metric] = {
            "alpha": best_alpha, "lolo_rmse": round(best_rmse, 4),
            "lolo_pearson_r": round(cv_r, 3), "n": len(mrows),
        }
        print(f"  {metric:14}  n={len(mrows):2}  alpha={best_alpha:6}  "
              f"RMSE={best_rmse:.3f}  r={cv_r:.3f}")

        for i, r in enumerate(mrows):
            all_cv_rows.append({
                "lang": r["lang"], "metric": metric,
                "bleu_r": f"{r['bleu_r']:.4f}",
                "metric_r": f"{r['spearman_r']:.4f}",
                "actual_advantage": f"{y[i]:.4f}",
                "predicted_advantage": f"{cv_preds[i]:.4f}",
                "resource_tier": r["resource_tier"],
                "morphology_type": r["morphology_type"],
                "direction": r["direction"],
            })

        for name, coef in zip(feat_names, beta):
            coef_rows.append({"metric": metric, "feature": name,
                               "coefficient": f"{coef:.5f}"})

    # ── Save CV predictions ────────────────────────────────────────────────────
    cv_path = os.path.join(out_dir, "cv_predictions.csv")
    with open(cv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_cv_rows[0].keys()))
        w.writeheader(); w.writerows(all_cv_rows)
    print(f"\n  Saved {cv_path}")

    # ── Save coefficients ──────────────────────────────────────────────────────
    coef_path = os.path.join(out_dir, "coefficients.csv")
    with open(coef_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["metric", "feature", "coefficient"])
        w.writeheader(); w.writerows(coef_rows)
    print(f"  Saved {coef_path}")

    # ── Recommendation table ───────────────────────────────────────────────────
    pred_adv   = {(r["lang"], r["metric"]): float(r["predicted_advantage"]) for r in all_cv_rows}
    actual_adv = {(r["lang"], r["metric"]): float(r["actual_advantage"])    for r in all_cv_rows}
    bleu_lookup = {r["lang"]: float(r["bleu_r"]) for r in all_cv_rows}
    meta = {r["lang"]: r for r in all_cv_rows}

    rec_path = os.path.join(out_dir, "recommendation_table.csv")
    with open(rec_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lang", "morphology_type", "direction", "resource_tier",
                    "word_order", "word_segmentation", "bleu_r"] +
                   [f"pred_adv_{m}" for m in metrics] +
                   ["recommended_metric", "pred_advantage_over_bleu",
                    "actual_best_metric", "actual_advantage_over_bleu"])
        for lang in langs_seen:
            lr = meta[lang]
            padv = {m: pred_adv[(lang, m)] for m in metrics if (lang, m) in pred_adv}
            aadv = {m: actual_adv[(lang, m)] for m in metrics if (lang, m) in actual_adv}
            if not padv:
                continue
            best_pred   = max(padv, key=padv.get)
            best_actual = max(aadv, key=aadv.get)
            # Find typological features from all_rows
            lang_row = next(r for r in all_rows if r["lang"] == lang)
            w.writerow([
                lang, lr["morphology_type"], lr["direction"], lr["resource_tier"],
                lang_row.get("word_order", ""), lang_row.get("word_segmentation", ""),
                f"{bleu_lookup[lang]:.4f}",
            ] + [f"{padv.get(m, ''):.4f}" if padv.get(m) is not None else "" for m in metrics] +
            [best_pred, f"{padv[best_pred]:.4f}", best_actual, f"{aadv[best_actual]:.4f}"])
    print(f"  Saved {rec_path}")

    # ── Summary ────────────────────────────────────────────────────────────────
    rec_rows = list(csv.DictReader(open(rec_path)))
    n_correct = sum(1 for r in rec_rows if r["recommended_metric"] == r["actual_best_metric"])
    print(f"\nRecommendation accuracy: {n_correct}/{len(rec_rows)} "
          f"({100*n_correct/len(rec_rows):.0f}%)")

    summary = {
        "n_langs": len(langs_seen), "n_metrics": len(metrics),
        "recommendation_accuracy": f"{n_correct}/{len(rec_rows)}",
        "per_metric": per_metric_summary,
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary written.")


if __name__ == "__main__":
    main()
