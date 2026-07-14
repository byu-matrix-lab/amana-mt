"""
Build typological_features.csv for all 31 languages in the benchmark.

Sources:
  - WALS (World Atlas of Language Structures) -- primary source
    Features used: 81A (word order), 49A (number of cases), 26A (prefix vs. suffix)
  - Manual annotation for languages missing from WALS (ht, kk, ps) and individual
    missing feature values (bn/26A, cs/49A, gu/26A, hi/49A, lo/49A, ta/49A, uk/49A, xh/49A)
    Manual values are flagged in the `source` column.

Feature codes (WALS):
  81A word_order:   1=SOV, 2=SVO, 3=VSO, 4=VOS, 5=OVS, 6=OSV, 7=No dominant order
  49A num_cases:    1=0, 2=2, 3=3, 4=4, 5=5, 6=6-7, 7=8-9, 8=10+, 9=borderline
  26A affix_direc:  1=Little affixation, 2=Strongly suffixing, 3=Weakly suffixing,
                    4=Equal, 5=Weakly prefixing, 6=Strong prefixing

word_segmentation: 1=spaces used as word boundaries, 0=no spaces (Thai, Lao, Khmer, Burmese,
                   Japanese, Chinese). Derived from script/writing system, not from WALS.
"""

import csv
import os

# ── WALS language IDs for our 31 ISO 639-1 codes ──────────────────────────────
ISO1_TO_WALS = {
    "am": "amh", "bn": "ben", "cs": "cze", "de": "ger", "et": "est",
    "fi": "fin", "fr": "fre", "gu": "guj", "ha": "hau", "hi": "hin",
    "ht": None,  "is": "ice", "ja": "jpn", "ka": "geo", "kk": None,
    "km": "khm", "lo": "lao", "lt": "lit", "lv": "lat", "my": "brm",
    "pl": "pol", "ps": None,  "ru": "rus", "sw": "swa", "ta": "tml",
    "th": "tha", "tr": "tur", "uk": "ukr", "xh": "xho", "zh": "mnd",
    "zu": "zul",
}

# ── Manual overrides for missing WALS values ──────────────────────────────────
# Format: (iso1, feature) -> value
# Sources: standard typological references (Comrie 1989, WALS chapters, Ethnologue)
MANUAL = {
    ("ht", "81A"): "2",   # Haitian Creole: SVO
    ("ht", "49A"): "1",   # no morphological case
    ("ht", "26A"): "1",   # little affixation (creole, highly analytic)
    ("kk", "81A"): "1",   # Kazakh: SOV (Turkic)
    ("kk", "49A"): "6",   # 6-7 cases (nominative, accusative, genitive, dative, locative, ablative)
    ("kk", "26A"): "2",   # strongly suffixing (Turkic agglutinative)
    ("ps", "81A"): "1",   # Pashto: SOV
    ("ps", "49A"): "5",   # 5 cases
    ("ps", "26A"): "2",   # suffixing
    ("bn", "26A"): "2",   # Bengali: suffixing
    ("bn", "49A"): "2",   # 2 cases (nominative/oblique distinction)
    ("cs", "49A"): "6",   # Czech: 7 cases
    ("gu", "26A"): "2",   # Gujarati: suffixing
    ("gu", "49A"): "3",   # 3 cases (direct, oblique, vocative)
    ("hi", "49A"): "3",   # Hindi: direct, oblique, vocative
    ("lo", "49A"): "1",   # Lao: no morphological case (isolating)
    ("ta", "49A"): "6",   # Tamil: 6-7 cases
    ("uk", "49A"): "6",   # Ukrainian: 7 cases
    ("xh", "49A"): "1",   # Xhosa: no morphological case (Bantu uses noun class agreement)
}

# ── Word segmentation: 0 = no orthographic spaces between words ───────────────
NO_WORD_SPACES = {"ja", "zh", "th", "lo", "km", "my"}

WALS_FEATURES = ["81A", "49A", "26A"]
FEATURE_NAMES = {"81A": "word_order", "49A": "num_cases", "26A": "affix_direc"}


def load_wals_values(wals_values_path, target_lang_ids, target_features):
    from collections import defaultdict
    values = defaultdict(dict)
    with open(wals_values_path) as f:
        for r in csv.DictReader(f):
            if r["Language_ID"] in target_lang_ids and r["Parameter_ID"] in target_features:
                values[r["Language_ID"]][r["Parameter_ID"]] = r["Value"]
    return values


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    wals_values_path = os.path.join(project_dir, "data", "grambank", "wals_values.csv")
    out_path = os.path.join(project_dir, "data", "typological_features.csv")

    wals_ids = {v for v in ISO1_TO_WALS.values() if v}
    wals_values = load_wals_values(wals_values_path, wals_ids, set(WALS_FEATURES))

    rows = []
    for iso1 in sorted(ISO1_TO_WALS):
        wals_id = ISO1_TO_WALS[iso1]
        row = {"lang": iso1, "word_segmentation": 0 if iso1 in NO_WORD_SPACES else 1}
        sources = []

        for feat in WALS_FEATURES:
            col = FEATURE_NAMES[feat]
            val = None
            src = None

            if wals_id and feat in wals_values.get(wals_id, {}):
                val = wals_values[wals_id][feat]
                src = "wals"
            elif (iso1, feat) in MANUAL:
                val = MANUAL[(iso1, feat)]
                src = "manual"

            row[col] = val if val is not None else ""
            if src == "manual":
                sources.append(f"{col}:manual")

        row["manual_fields"] = "|".join(sources)
        rows.append(row)

    fieldnames = ["lang", "word_segmentation", "word_order", "num_cases", "affix_direc", "manual_fields"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_path}")
    # Print summary
    for col in ["word_order", "num_cases", "affix_direc"]:
        n_missing = sum(1 for r in rows if not r[col])
        print(f"  {col}: {len(rows) - n_missing}/{len(rows)} complete")


if __name__ == "__main__":
    main()
