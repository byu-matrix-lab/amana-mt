"""Rescore sentence BLEU with FLORES-200 SentencePiece tokenization for targets
whose script has no spaces between words (2026-11-16, corrected paper v2).

sacreBLEU's default 13a tokenizer splits on whitespace and punctuation. For
Japanese, Thai, Lao and Burmese targets almost nothing is split, so BLEU is
near zero whatever the quality (en-ja BLEU vs DA: rho = -.000). This script
rewrites results/scores_bleu.csv for those rows only, using
sacrebleu.BLEU(tokenize="flores200") (spBLEU). Every other row keeps 13a.

Safety: for each block the script first recomputes 13a BLEU on the texts it
matched and requires it to equal the stored BLEU on >= 99.9% of rows. That
proves the texts are aligned with the stored rows before anything is replaced.
A backup of the original file is written once.

    PYTHONPATH=src .venv/bin/python scripts/rescore_bleu_spm.py [--dry-run]
"""
import argparse
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import sacrebleu

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mqmbench.config import init_settings  # noqa: E402
from mqmbench.data.utils import read_jsonl_cache  # noqa: E402
from mqmbench.data.wmt_da import load_wmt_da  # noqa: E402

SPM_TARGETS = ("ja", "th", "lo", "my")
SCORES = ROOT / "results" / "scores_bleu.csv"
BACKUP = ROOT / "results" / "backup_pre_spbleu_2026-11-16" / "scores_bleu.csv"
B13A = sacrebleu.BLEU(effective_order=True)              # built once: sentence_bleu reloads per call
BSPM = sacrebleu.BLEU(tokenize="flores200", effective_order=True)


def _bleu(scorer, hyps, refs):
    return np.array([scorer.sentence_score(h, [r]).score / 100.0 for h, r in zip(hyps, refs)])


def _check_and_rescore(name, stored, hyps, refs):
    recomputed = _bleu(B13A, hyps, refs)
    match = float(np.isclose(recomputed, stored, atol=1e-9).mean())
    print(f"{name}: {len(stored)} rows; 13a recompute == stored: {match:.4f}")
    if match < 0.999:
        raise SystemExit(f"{name}: texts are not aligned with scores_bleu.csv; refusing to rescore")
    new = _bleu(BSPM, hyps, refs)
    print(f"  mean BLEU 13a {stored.mean():.4f} -> spBLEU {new.mean():.4f}")
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    init_settings(str(ROOT / "settings.toml"))
    d = pd.read_csv(SCORES)
    if BACKUP.exists():
        orig = pd.read_csv(BACKUP)
        if len(orig) != len(d) or not (orig.segment_id.values == d.segment_id.values).all():
            raise SystemExit("backup does not match scores_bleu.csv row-for-row")
        d["bleu"] = orig["bleu"].values   # always start from the original 13a scores
    new = d["bleu"].to_numpy(dtype=float).copy()

    # Tier 2 (synthetic, en->X): texts from the NLLB cache, matched on segment_id.
    cache = ROOT / "data" / "cache"
    for lang in ("th", "lo", "my"):
        rows = pd.DataFrame(read_jsonl_cache(cache / f"nllb_hypotheses_{lang}.jsonl"))
        rows = rows.drop_duplicates("segment_id").set_index("segment_id")
        mask = (d.lang == lang) & (d.annotation_tier == "synthetic_mqm")
        ids = d.loc[mask, "segment_id"]
        if not ids.isin(rows.index).all():
            raise SystemExit(f"{lang}: segment_ids missing from the NLLB cache")
        hyps = rows.loc[ids, "hypothesis"].fillna("").astype(str).tolist()
        refs = rows.loc[ids, "reference"].fillna("").astype(str).tolist()
        new[mask.to_numpy()] = _check_and_rescore(f"en-{lang} (Tier 2)", d.loc[mask, "bleu"].to_numpy(), hyps, refs)

    # en-ja (WMT DA): positional, exactly as the pipeline loads it.
    ja = load_wmt_da(target_langs=["ja"]).reset_index(drop=True)
    mask_ja = (d.lang == "ja").to_numpy()
    if mask_ja.sum() != len(ja):
        raise SystemExit(f"ja: {mask_ja.sum()} score rows vs {len(ja)} loaded rows")
    en_ja = ja.segment_id.str.startswith("en-ja").to_numpy()
    idx = np.flatnonzero(mask_ja)[en_ja]
    if not d.segment_id.iloc[idx].str.startswith("en-ja").all():
        raise SystemExit("ja: positional alignment mismatch on direction")
    hyps = ja.hypothesis[en_ja].fillna("").astype(str).tolist()
    refs = ja.reference[en_ja].fillna("").astype(str).tolist()
    new[idx] = _check_and_rescore("en-ja", d.bleu.to_numpy()[idx], hyps, refs)

    if args.dry_run:
        print("dry run: nothing written")
        return
    if not BACKUP.exists():
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCORES, BACKUP)
    d["bleu"] = new
    d.to_csv(SCORES, index=False)
    print(f"wrote {SCORES} ({int((new != pd.read_csv(BACKUP).bleu.to_numpy()).sum())} rows changed); backup at {BACKUP}")


if __name__ == "__main__":
    main()
