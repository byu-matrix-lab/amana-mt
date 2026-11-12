"""Assert every numerical invariant the paper depends on.

Run from project root:
    python scripts/assert_paper_invariants.py

Exits 0 if all checks pass; exits 1 on first failure (with a descriptive message).
Covers:
  A. TIER2_LANGS excluded from all Tier-1 cell means
  B. Every Tier-1 language in exactly one direction group (no double-counting)
  C. Cell n's match the claimed values
  D. macros_generated.tex values match freshly-computed CSV values (within 0.001)
  E. Table 1 (tier_summary.csv) excludes synthetic_mqm rows
  F. Direction assignments: TRANSLATION_DIRECTIONS is internally consistent
  G. Main claim invariants: EtaSqDir > EtaSqMorph; en→X > X→en for both morph types
  H. Table 6 (per-language direction appendix): each lang's direction tag matches CSV
"""

import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from mqmbench.analysis.correlation import (
    MORPHOLOGY_TYPES, TRANSLATION_DIRECTIONS, TIER2_LANGS,
)
from generate_paper_stats import build_corrected_lang_dir_rho

RESULTS = ROOT / "results"
LATEX   = ROOT / os.environ.get("PAPER_DIR", "latex")  # 2026-11-09: see render_macros.py

from mqmbench.analysis.correlation import MIXED_DIRECTION_LANGS as MIXED_LANGS  # single source (2026-11-09)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  {PASS}  {name}")
    else:
        msg = f"{name}" + (f": {detail}" if detail else "")
        print(f"  {FAIL}  {msg}")
        failures.append(msg)


def approx_eq(a: float, b: float, tol: float = 0.001) -> bool:
    return abs(a - b) <= tol


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_macros(path: Path) -> dict[str, float]:
    """Parse \\newcommand{\\Name}{value} from a .tex file."""
    macros = {}
    for line in path.read_text().splitlines():
        m = re.match(r'\\newcommand\{\\(\w+)\}\{([0-9.\-]+)\}', line)
        if m:
            macros[m.group(1)] = float(m.group(2))
    return macros


def build_tier1_lang_dir_rho(metric: str = "comet") -> pd.DataFrame:
    """Delegate to the canonical recompute script (imports build_corrected_lang_dir_rho)."""
    return build_corrected_lang_dir_rho(metric)


# ─────────────────────────────────────────────────────────────────────────────
print("\n=== A. TIER2_LANGS not in any Tier-1 cell ===")
# ─────────────────────────────────────────────────────────────────────────────

df_t1 = build_tier1_lang_dir_rho("comet")
# Strip direction suffix added for mixed langs (e.g. "fi_en_" → "fi")
base_langs = {re.sub(r"_\w+$", "", l) for l in df_t1["lang"]}
leaked = TIER2_LANGS & base_langs
check("No Tier-2 lang in Tier-1 rho table", not leaked,
      f"leaked: {leaked}")

da = pd.read_csv(RESULTS / "direction_analysis.csv")
tier2_in_da_t1 = set(da[da.lang.isin(TIER2_LANGS) & (da.domain != "unknown")]["lang"].unique())
check("Tier-2 langs have domain=unknown (da_df filter correct)", not tier2_in_da_t1,
      f"domain!=unknown: {tier2_in_da_t1}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n=== B. Direction groups: no double-counting ===")
# ─────────────────────────────────────────────────────────────────────────────

all_dir_langs: list[str] = []
for langs in TRANSLATION_DIRECTIONS.values():
    all_dir_langs.extend(langs)
duplicates = {l for l in all_dir_langs if all_dir_langs.count(l) > 1}
check("No lang in multiple direction groups", not duplicates,
      f"duplicates: {duplicates}")

all_morph_langs: list[str] = []
for langs in MORPHOLOGY_TYPES.values():
    all_morph_langs.extend(langs)
morph_dups = {l for l in all_morph_langs if all_morph_langs.count(l) > 1}
check("No lang in multiple morphology groups", not morph_dups,
      f"duplicates: {morph_dups}")

# TIER2_LANGS must be a subset of TRANSLATION_DIRECTIONS["en_to_x"]
tier2_not_in_en_to_x = TIER2_LANGS - set(TRANSLATION_DIRECTIONS["en_to_x"])
check("All TIER2_LANGS are in en_to_x direction", not tier2_not_in_en_to_x,
      f"not in en_to_x: {tier2_not_in_en_to_x}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n=== C. Cell n's match claimed values ===")
# ─────────────────────────────────────────────────────────────────────────────

EXPECTED_CELLS = {
    # ha moved agglutinative -> fusional (see analyze_direction_separated.py);
    # counts shifted by one in both directions accordingly.
    ("en_to_x", "agglutinative"): 6,
    ("en_to_x", "fusional"):      10,
    ("x_to_en", "isolating"):     2,
    ("x_to_en", "agglutinative"): 6,
    ("x_to_en", "fusional"):      9,
    ("pivot",   "fusional"):      5,
}

for (direction, morph), expected_n in EXPECTED_CELLS.items():
    subset = df_t1[(df_t1.direction == direction) & (df_t1.morphology == morph)]
    actual_n = len(subset)
    check(f"Cell n: {direction}×{morph} = {expected_n}",
          actual_n == expected_n,
          f"got {actual_n}, langs={sorted(subset.lang.tolist())}")

total_claimed = sum(EXPECTED_CELLS.values())
total_actual  = len(df_t1)
check(f"Total Tier-1 lang-direction entries = {total_claimed}",
      total_actual == total_claimed,
      f"got {total_actual}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n=== D. macros_generated.tex values match CSV ===")
# ─────────────────────────────────────────────────────────────────────────────

macros = load_macros(LATEX / "macros_generated.tex")

# Check cell means
DIR_KEY  = {"en_to_x": "EntoX", "x_to_en": "XtoEn", "pivot": "Pivot"}
MORPH_KEY = {"agglutinative": "Agglutin", "fusional": "Fusional", "isolating": "Isolating"}

for (direction, morph) in EXPECTED_CELLS:
    subset = df_t1[(df_t1.direction == direction) & (df_t1.morphology == morph)]
    if subset.empty:
        continue
    computed = float(subset.spearman_r.mean())
    dk, mk = DIR_KEY[direction], MORPH_KEY[morph]
    macro_name = f"DirMorphCOMET{dk}{mk}"
    if macro_name not in macros:
        check(f"Macro {macro_name} exists", False, "missing from macros_generated.tex")
        continue
    check(f"Macro {macro_name} ≈ {computed:.3f}",
          approx_eq(macros[macro_name], computed),
          f"macro={macros[macro_name]:.3f} vs computed={computed:.3f}")

# Check direction×metric means (DirMetric*) — use same build_corrected_lang_dir_rho
TABLE3_METRICS = {"bleu": "BLEU", "chrf": "ChrF", "comet": "COMET",
                  "xcomet": "xCOMET", "metricx": "MetricX"}
for metric, mk3 in TABLE3_METRICS.items():
    df_m = build_corrected_lang_dir_rho(metric)
    df_m = df_m[df_m["direction"].isin(["en_to_x", "x_to_en", "pivot"])]
    for direction, dk in DIR_KEY.items():
        vals = df_m[df_m["direction"] == direction]["spearman_r"].dropna()
        if vals.empty:
            continue
        computed = float(vals.mean())
        macro_name = f"DirMetric{mk3}{dk}"
        if macro_name not in macros:
            check(f"Macro {macro_name} exists", False, "missing from macros_generated.tex")
            continue
        check(f"Macro {macro_name} ≈ {computed:.3f}",
              approx_eq(macros[macro_name], computed),
              f"macro={macros[macro_name]:.3f} vs computed={computed:.3f}")

# Check η² values — recompute script excludes pivot, matches compute_eta_sq()
df_for_eta = df_t1[df_t1["direction"].isin(["x_to_en", "en_to_x"])].copy()
y       = df_for_eta["spearman_r"].dropna().values
gm      = y.mean()
ss_tot  = ((y - gm) ** 2).sum()
dir_means  = df_for_eta.groupby("direction")["spearman_r"].mean()
morph_means = df_for_eta.groupby("morphology")["spearman_r"].mean()
ss_dir  = sum((df_for_eta["direction"] == d).sum() * (m - gm) ** 2 for d, m in dir_means.items())
ss_morph = sum((df_for_eta["morphology"] == mt).sum() * (m - gm) ** 2 for mt, m in morph_means.items())
eta_dir   = ss_dir / ss_tot
eta_morph = ss_morph / ss_tot
# Between-cell eta^2 (fixed 2026-11-09; previously replicated the residual
# 1 - eta_dir - eta_morph, so this check could never catch that bug).
_cells = df_for_eta.groupby(["direction", "morphology"])["spearman_r"].agg(["mean", "size"])
eta_cell = float((_cells["size"] * (_cells["mean"] - gm) ** 2).sum() / ss_tot)

check(f"EtaSqDir macro ≈ {eta_dir:.3f}",
      approx_eq(macros.get("EtaSqDir", -1), eta_dir),
      f"macro={macros.get('EtaSqDir','?')} vs computed={eta_dir:.3f}")
check(f"EtaSqMorph macro ≈ {eta_morph:.3f}",
      approx_eq(macros.get("EtaSqMorph", -1), eta_morph),
      f"macro={macros.get('EtaSqMorph','?')} vs computed={eta_morph:.3f}")
check(f"EtaSqCell macro ≈ {eta_cell:.3f}",
      approx_eq(macros.get("EtaSqCell", -1), eta_cell),
      f"macro={macros.get('EtaSqCell','?')} vs computed={eta_cell:.3f}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n=== E. Table 1: tier_summary.csv excludes synthetic_mqm ===")
# ─────────────────────────────────────────────────────────────────────────────

tier_df = pd.read_csv(RESULTS / "tier_summary.csv")
tiers_present = set(tier_df["annotation_tier"].unique())
check("tier_summary.csv still tags synthetic_mqm rows (sanity check on raw data)",
      "synthetic_mqm" in tiers_present,
      f"found: {tiers_present} — if synthetic_mqm is gone, the exclusion filter below is a no-op")

# The real invariant: generate_paper_stats.py must filter synthetic_mqm out
# before building Table 1 macros. Static-check the source for the filter
# line, since paper_stats.json doesn't retain which annotation_tier rows
# were averaged.
gen_macros_src = (ROOT / "scripts" / "generate_paper_stats.py").read_text()
check('generate_paper_stats.py filters annotation_tier != "synthetic_mqm" for Table 1',
      'annotation_tier != "synthetic_mqm"' in gen_macros_src,
      "filter line missing — Table 1 may be contaminated by synthetic MQM langs")

# macros.tex TierBLEU* should match tier_summary for human tiers
for ann_tier, at_label in [("human_mqm", "Mqm"), ("human_da", "Da")]:
    for res_tier, rt_label in [("high", "High"), ("medium", "Medium"), ("low", "Low")]:
        row = tier_df[(tier_df.annotation_tier == ann_tier) &
                      (tier_df.resource_tier == res_tier) &
                      (tier_df.metric == "comet")]
        if row.empty:
            continue
        rho = float(row.iloc[0]["spearman_r"])
        # Macros file uses e.g. TierCOMETHighRho (annotation tier not in macro name for DA)
        # Just verify the value is plausible (positive, in [−1,1])
        check(f"Tier COMET {res_tier}/{ann_tier} rho plausible ({rho:.3f})",
              -1 <= rho <= 1,
              f"out of range: {rho}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n=== F. Direction assignments: TRANSLATION_DIRECTIONS internal consistency ===")
# ─────────────────────────────────────────────────────────────────────────────

dir_df = da[(da.metric == "comet")][["lang", "direction"]].drop_duplicates()
lang_to_dir_csv = dict(zip(dir_df.lang, dir_df.direction))
lang_to_dir_code = {l: d for d, langs in TRANSLATION_DIRECTIONS.items() for l in langs}

mismatches = []
for lang, dir_code in lang_to_dir_code.items():
    if lang in MIXED_LANGS:
        continue  # mixed langs will have both directions in CSV
    dir_csv = lang_to_dir_csv.get(lang)
    if dir_csv and dir_csv != dir_code:
        mismatches.append(f"{lang}: code={dir_code}, csv={dir_csv}")

check("Direction assignments match direction_analysis.csv (non-mixed langs)",
      not mismatches,
      "; ".join(mismatches))


# ─────────────────────────────────────────────────────────────────────────────
print("\n=== G. Main claim invariants ===")
# ─────────────────────────────────────────────────────────────────────────────

# Direction dominates morphology
eta_dir_m  = macros.get("EtaSqDir", 0.0)
eta_morph_m = macros.get("EtaSqMorph", 1.0)
check(f"EtaSqDir ({eta_dir_m:.3f}) > EtaSqMorph ({eta_morph_m:.3f})",
      eta_dir_m > eta_morph_m)

# en→X > X→en for COMET (both agglutin and fusional)
entox_agg = macros.get("DirMorphCOMETEntoXAgglutin", 0.0)
xtoen_agg = macros.get("DirMorphCOMETXtoEnAgglutin", 1.0)
entox_fus = macros.get("DirMorphCOMETEntoXFusional", 0.0)
xtoen_fus = macros.get("DirMorphCOMETXtoEnFusional", 1.0)
check(f"en→X agglutin ({entox_agg:.3f}) > X→en agglutin ({xtoen_agg:.3f})",
      entox_agg > xtoen_agg)
check(f"en→X fusional ({entox_fus:.3f}) > X→en fusional ({xtoen_fus:.3f})",
      entox_fus > xtoen_fus)

# DiD = (fusional dir gap) − (agglutin dir gap)
did = (entox_fus - xtoen_fus) - (entox_agg - xtoen_agg)
_did_m = macros.get("DiDValue", float("nan"))
check(f"DiD recomputed from cell macros ({did:.3f}) = DiDValue macro ({_did_m:.3f})",
      approx_eq(did, _did_m, tol=0.0015),
      f"computed DiD={did:.3f}")

# Ridge predictor: CK Pearson r plausible
predictor_summary = RESULTS / "predictor" / "summary.json"
if predictor_summary.exists():
    import json
    summary = json.loads(predictor_summary.read_text())
    ck_r = summary["per_metric"].get("cometkiwi", {}).get("lolo_pearson_r", None)
    ck23_r = summary["per_metric"].get("cometkiwi23", {}).get("lolo_pearson_r", None)
    n_langs = summary.get("n_langs", 0)
    # 2026-11-10: compare against the SSOT macros instead of hand-typed values.
    _macro_txt = (LATEX / "macros_generated.tex").read_text()
    def _macro_str(name):
        m = re.search(r"\\newcommand\{\\" + name + r"\}\{([^}]*)\}", _macro_txt)
        return m.group(1) if m else None
    check(f"Ridge n_langs ({n_langs}) = RidgeNLangs macro", str(n_langs) == _macro_str("RidgeNLangs"),
          f"macro {_macro_str('RidgeNLangs')}")
    if ck_r is not None:
        check(f"Ridge CK Pearson r ({ck_r:.3f}) = RidgeCKPearson macro",
              f"{ck_r:.2f}" == _macro_str("RidgeCKPearson") or f"{ck_r:.3f}".lstrip("0") == _macro_str("RidgeCKPearson"),
              f"macro {_macro_str('RidgeCKPearson')}")
    if ck23_r is not None:
        check(f"Ridge CK23 Pearson r ({ck23_r:.3f}) = RidgeCKXXIIIPearson macro",
              f"{ck23_r:.2f}" == _macro_str("RidgeCKXXIIIPearson") or f"{ck23_r:.3f}".lstrip("0") == _macro_str("RidgeCKXXIIIPearson"),
              f"macro {_macro_str('RidgeCKXXIIIPearson')}")
    rec = summary.get("recommendation_accuracy", "")
    check(f"Recommendation accuracy ({rec}) = RidgeRecAcc macro", rec == _macro_str("RidgeRecAcc"),
          f"macro {_macro_str('RidgeRecAcc')}")
else:
    print(f"  SKIP  predictor/summary.json not found")


# ─────────────────────────────────────────────────────────────────────────────
print("\n=== H. Table 6: direction_analysis.csv lang→direction consistent ===")
# ─────────────────────────────────────────────────────────────────────────────

# Every language in direction_analysis.csv that is NOT mixed should have
# exactly one direction, matching TRANSLATION_DIRECTIONS
multi_dir_langs = (
    da[~da.lang.isin(MIXED_LANGS)].groupby("lang")["direction"].nunique()
)
confused = multi_dir_langs[multi_dir_langs > 1]
check("Non-mixed langs have exactly one direction in direction_analysis.csv",
      confused.empty,
      f"multiple dirs: {confused.index.tolist()}")

# direction_analysis.csv pools mixed-direction langs into one row (by design —
# that's WHY they're "mixed" and require direction_separated_correlations.csv).
# The real invariant lives there: MIXED_LANGS must have exactly 2 directions each.
sep_df = pd.read_csv(RESULTS / "direction_separated_correlations.csv")
mixed_dir_counts = (
    sep_df[sep_df.lang.isin(MIXED_LANGS) & (sep_df.metric == "comet")]
    .groupby("lang")["direction"].nunique()
)
wrong_mixed = mixed_dir_counts[mixed_dir_counts != 2]
missing_mixed = MIXED_LANGS - set(mixed_dir_counts.index)
check("Mixed langs have exactly 2 directions in direction_separated_correlations.csv",
      wrong_mixed.empty and not missing_mixed,
      f"wrong counts: {wrong_mixed.to_dict()}, missing: {missing_mixed}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n=== I0. macros_generated.tex is well-formed (brace-balanced) ===")
# ─────────────────────────────────────────────────────────────────────────────
# Catches the exact bug that shipped once: a naive [^}]* regex in the
# JSON-merge step of recompute_dir_morph_table.py / generate_yearstrat_macros.py
# truncated every N-count macro at LaTeX's {,} thousand-separator idiom
# (e.g. "15{,}600" -> "15{,}"), silently corrupting the JSON and producing a
# macros_generated.tex that failed to compile with "File ended while
# scanning use of \@argdef" and hundreds of cascading "Undefined control
# sequence" errors. A brace-balance check on the rendered file is a cheap,
# permanent tripwire for this whole failure class, independent of whether
# the specific parsing bug that caused it has been fixed.
# ─────────────────────────────────────────────────────────────────────────────
macros_text = (LATEX / "macros_generated.tex").read_text()
depth = 0
min_depth_ok = True
for ch in macros_text:
    if ch == "{":
        depth += 1
    elif ch == "}":
        depth -= 1
    if depth < 0:
        min_depth_ok = False
        break
check(f"macros_generated.tex braces balanced (final depth={depth})",
      min_depth_ok and depth == 0,
      "unbalanced braces — a macro value was likely truncated during JSON round-trip")

# ─────────────────────────────────────────────────────────────────────────────
# Catches the other bug that shipped twice in one night: a macro NAME
# containing a digit (SepCK23FIXE, Table4MainPipelinePairs, RidgeCK23Pearson).
# LaTeX control words are letters-only — TeX reads \SepCK23KKEX as \SepCK
# followed by literal text "23KKEX", not as one identifier. This is invisible
# in the Python source (a perfectly normal-looking dict key) and only
# surfaces as a cryptic pdflatex error ("Missing number, treated as zero",
# "Undefined control sequence") with no obvious connection to the macro name.
# ─────────────────────────────────────────────────────────────────────────────
digit_macro_names = sorted(set(re.findall(r"\\newcommand\{\\([A-Za-z]*[0-9][A-Za-z0-9]*)\}", macros_text)))
check(f"No macro names contain digits (found {len(digit_macro_names)})",
      not digit_macro_names,
      f"LaTeX control words are letters-only; these break silently: {digit_macro_names}")


print("\n=== I. Every table row cites a real, sourced language/pair ===")
# ─────────────────────────────────────────────────────────────────────────────
# Catches the de-cs class of bug: a row hand-typed into a LaTeX table whose
# row label doesn't correspond to any language/pair this pipeline has ever
# scored. Existing invariants (A-H) verify AGGREGATES and cell membership —
# none of them would have caught a fabricated row sitting by itself in an
# appendix table that nothing sums over. This check parses every
# "label & ... \\" table row in main.tex and requires the row's language/pair
# label to appear in one of: TRANSLATION_DIRECTIONS langs, MIXED_LANGS,
# TIER2_LANGS, or an explicit, disclosed held-out-pair allowlist.

HELD_OUT_PAIRS = {"de-en"}  # blind validation pairs explicitly discussed in prose
ALL_KNOWN_LANGS = set(lang_to_dir_code.keys()) | MIXED_LANGS | TIER2_LANGS

main_tex_path = LATEX / "main.tex"
main_tex_text = main_tex_path.read_text()

# Match simple table rows: "xx-yy & ... \\" or "xx & ... \\" at line start,
# where xx(-yy) looks like a language/pair code (lowercase letters/hyphen,
# 2-7 chars), not a prose sentence. Restricted to table-row-shaped lines
# (contains " & " and ends in "\\") to avoid matching prose.
ROW_RE = re.compile(r"^([a-z]{2}(?:-[a-z]{2})?)(\^[\\\w{}]*)?\s*&.*\\\\\s*$")

suspect_rows = []
for line in main_tex_text.split("\n"):
    line_stripped = line.strip()
    if " & " not in line_stripped or not line_stripped.endswith(r"\\"):
        continue
    m = ROW_RE.match(line_stripped)
    if not m:
        continue
    label = m.group(1)
    # Strip a possible direction suffix like "-en" or a "en-" prefix to get
    # the base language code for cross-referencing against known langs.
    if label in HELD_OUT_PAIRS:
        continue
    base = label
    if "-" in label:
        a, b = label.split("-")
        base = a if b == "en" else (b if a == "en" else label)
    if base not in ALL_KNOWN_LANGS and label not in ALL_KNOWN_LANGS:
        suspect_rows.append((label, line_stripped[:80]))

check(f"No table rows cite an unknown language/pair (found {len(suspect_rows)} suspect)",
      not suspect_rows,
      "; ".join(f"'{lbl}' in: {ctx}" for lbl, ctx in suspect_rows))


# ─────────────────────────────────────────────────────────────────────────────
print("\n=== J. Morphology classification has exactly one source of truth ===")
# ─────────────────────────────────────────────────────────────────────────────
# Guards against the Hausa bug: a reviewer caught that Table 6 (fusional) and
# Table 4/7 (agglutinative, via direction_separated_correlations.csv) disagreed
# on Hausa's morphology type, because that CSV's own generating script kept an
# independent, hand-typed copy of the morphology dict that had drifted from the
# canonical MORPHOLOGY_TYPES. Both are now derived from one dict, but a future
# edit could reintroduce a second hardcoded copy without anyone noticing — this
# check makes that impossible to miss.
_lang_to_morph_canonical = {lang: m for m, langs in MORPHOLOGY_TYPES.items() for lang in langs}
_sep_df = pd.read_csv(RESULTS / "direction_separated_correlations.csv")
_mismatches = []
for lang in sorted(_sep_df["lang"].unique()):
    csv_morph = _sep_df.loc[_sep_df["lang"] == lang, "morphology"].iloc[0]
    canon_morph = _lang_to_morph_canonical.get(lang)
    if canon_morph is not None and csv_morph != canon_morph:
        _mismatches.append(f"{lang}: csv={csv_morph} canonical={canon_morph}")

check(f"direction_separated_correlations.csv morphology matches MORPHOLOGY_TYPES (found {len(_mismatches)} mismatches)",
      not _mismatches,
      "; ".join(_mismatches))

# ─────────────────────────────────────────────────────────────────────────────
print("\n=== K. Every macro used in main.tex is actually defined ===")
# Caught by hand on 2026-09-11 when a real pdflatex compile (previously
# unavailable in this environment) surfaced \TierGEMBAMedRho: a macro cited in
# a table caption that generate_paper_stats.py never generated, left over from
# an earlier paper draft. Nothing here would have caught it -- checks D/G/etc.
# only verify macros that exist actually have correct values, not that every
# macro *referenced in the prose* exists at all. This makes that silent-drift
# failure mode permanently visible without needing a LaTeX compiler on hand.
# ─────────────────────────────────────────────────────────────────────────────
_main_tex = (LATEX / "main.tex").read_text()
_macros_tex = (LATEX / "macros_generated.tex").read_text()
_lang_table_path = LATEX / "language_table_generated.tex"
_lang_table_tex = _lang_table_path.read_text() if _lang_table_path.exists() else ""

_defined = set(re.findall(r"\\newcommand\{\\(\w+)\}", _macros_tex))
_defined |= set(re.findall(r"\\newcommand\{\\(\w+)\}", _lang_table_tex))
_defined |= set(re.findall(r"\\(?:newcommand|providecommand)\{\\(\w+)\}", _main_tex))

_used = set(re.findall(r"\\([A-Za-z]+)", _main_tex))
_STANDARD_LATEX = {
    "textbf", "textit", "emph", "label", "ref", "cite", "citet", "citep", "S",
    "section", "subsection", "subsubsection", "begin", "end", "item",
    "includegraphics", "caption", "footnote", "url", "texttt", "paragraph",
    "noindent", "centering", "toprule", "midrule", "bottomrule", "multirow",
    "multicolumn", "hline", "newcommand", "providecommand", "documentclass",
    "usepackage", "title", "author", "date", "maketitle", "bibliography",
    "bibliographystyle", "appendix", "rho", "times", "mathcal", "mathbb",
    "rangle", "langle", "Delta", "sigma", "eta", "emptyset", "infty",
    "approx", "leq", "geq", "neq", "cdot", "to", "leftrightarrow", "gg",
    "ll", "sim", "propto", "forall", "exists", "in", "notin", "subset",
    "supset", "cup", "cap", "text", "emph", "star", "input",
}
# SSOT macros follow a CamelCase convention; this heuristic avoids flagging
# ordinary LaTeX control words while still catching orphaned SSOT references.
_candidates = sorted(
    u for u in _used
    if u not in _STANDARD_LATEX and u not in _defined and len(u) > 3 and u[0].isupper()
)
check(f"No undefined SSOT-style macros referenced in main.tex (found {len(_candidates)})",
      not _candidates,
      ", ".join(_candidates))

# ─────────────────────────────────────────────────────────────────────────────
print("\n=== L. Every embedded figure matches its results/plots/ source ===")
# make_presentation_plots.py writes to results/plots/, but \includegraphics
# in main.tex reads from latex/figures/ -- a separate directory nothing
# copies into automatically. Found 2026-09-11: latex/figures/ held PDFs over
# a month stale (including one with a retracted claim still visible) while
# results/plots/ had the corrected versions, and the mismatch was invisible
# to every check above since none of them look at figure *files*, only
# macros and table rows. scripts/build_paper.sh now copies results/plots/
# over latex/figures/ before every compile; this check exists so a manual
# pdflatex run (bypassing that script) still gets caught.
# ─────────────────────────────────────────────────────────────────────────────
import hashlib

def _md5(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

_fig_refs = sorted(set(re.findall(r"figures/([A-Za-z0-9_]+\.pdf)", _main_tex)))
_stale_figs = []
for fname in _fig_refs:
    embedded = LATEX / "figures" / fname
    source = RESULTS / "plots" / fname
    if not source.exists():
        _stale_figs.append(f"{fname}: no source in results/plots/")
    elif not embedded.exists():
        _stale_figs.append(f"{fname}: referenced in main.tex but missing from latex/figures/")
    elif _md5(embedded) != _md5(source):
        _stale_figs.append(f"{fname}: latex/figures/ copy does not match results/plots/ source")
check(f"All {len(_fig_refs)} embedded figures match their results/plots/ source (found {len(_stale_figs)} stale)",
      not _stale_figs,
      "; ".join(_stale_figs))

# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M. Metric scope (2026-11-10): GEMBA excluded, BLEURT English-target only ===")
# See src/mqmbench/analysis/metric_scope.py. GEMBA is degenerate (99.6% of
# segments score "no errors") and is excluded from every analysis. BLEURT
# (English BLEURT-large port) is reported only where the target is English.
# ─────────────────────────────────────────────────────────────────────────────
_corr_full = pd.read_csv(RESULTS / "correlations.csv")
check("GEMBA absent from correlations.csv", not (_corr_full.metric == "gemba").any(),
      f"found {int((_corr_full.metric == 'gemba').sum())} GEMBA rows")
_tex_no_vnote = re.sub(r"\\noindent\\textbf\{Version note\.\}.*?\n\n", "", main_tex_text, flags=re.S)
check("GEMBA not mentioned in main.tex outside the version note", "GEMBA" not in _tex_no_vnote,
      "main.tex still mentions GEMBA")
_ds = pd.read_csv(RESULTS / "direction_separated_correlations.csv")
_bad_bleurt = _ds[(_ds.metric == "bleurt") & (_ds.direction != "x_to_en")]
check("BLEURT appears only for X->en in direction_separated_correlations.csv", _bad_bleurt.empty,
      f"found {len(_bad_bleurt)} non-X->en BLEURT rows")
_bleurt_langs = set(_corr_full[(_corr_full.metric == "bleurt") & _corr_full.spearman_r.notna()].lang)
_no_en_target = {"es", "ru", "de", "lv", "fr", "bn", "hi", "xh", "zu"} | set(TIER2_LANGS)
check("No BLEURT correlation for languages with no English-target rows",
      not (_bleurt_langs & _no_en_target), f"found {sorted(_bleurt_langs & _no_en_target)}")

print("\n=== N. Table direction_full's hand-placed COMET/MetricX bold markers match the data ===")
# main.tex's per-language COMET-vs-MetricX table (\label{tab:direction_full})
# bolds whichever metric wins each row by hand -- LaTeX has no conditional
# bold, so this can't be a macro, but it's exactly the kind of hand-typed
# claim ("MetricX wins all but two languages: ru, he") this project's SSOT
# discipline exists to catch if it goes stale after a data refresh.
# Languages with data in both directions (MIXED_LANGS) are shown in Table 7
# under ONE direction section, using THAT direction's value (found 2026-09-12:
# it previously showed a pooled, direction-blended value that didn't match
# Table 8/Table 2's direction-separated numbers for the same language, e.g.
# kk-en COMET 0.519 vs. the pooled 0.613) -- so this check must compare
# against the same direction-specific values, not the pooled correlations.csv.
_mixed_lang_display_direction = {
    "fi": "en_to_x", "tr": "en_to_x", "et": "en_to_x", "lt": "en_to_x",
    "cs": "en_to_x", "ja": "en_to_x", "ta": "en_to_x", "ha": "en_to_x",
    "pl": "en_to_x", "is": "en_to_x", "kk": "x_to_en", "gu": "x_to_en",
}
_t1_corr = _corr_full[_corr_full.annotation_tier != "synthetic_mqm"]
_comet_s = _t1_corr[_t1_corr.metric == "comet"].set_index("lang").spearman_r.to_dict()
_metricx_s = _t1_corr[_t1_corr.metric == "metricx"].set_index("lang").spearman_r.to_dict()
_sep_full = pd.read_csv(RESULTS / "direction_separated_correlations.csv")
for _l, _d in _mixed_lang_display_direction.items():
    for _metric_name, _target in (("comet", _comet_s), ("metricx", _metricx_s)):
        _row = _sep_full[(_sep_full.lang == _l) & (_sep_full.direction == _d) & (_sep_full.metric == _metric_name)]
        if not _row.empty:
            _target[_l] = _row.spearman_r.iloc[0]
_direction_full_langs = ["lv", "lt", "et", "fi", "es", "cs", "tr", "ta", "pl", "de", "is", "ja", "ha", "ru",
                          "kk", "gu", "km", "zh", "he", "ps", "uk", "xh", "fr", "zu", "bn", "hi"]
_comet_wins = sorted(l for l in _direction_full_langs if _comet_s[l] > _metricx_s[l])
# 2026-11-10: read the bold markers from main.tex itself instead of a hand-typed set.
_tbl = main_tex_text[:main_tex_text.index("\\label{tab:direction_full}")]
_tbl = _tbl[_tbl.rindex("\\begin{tabular}"):]
_bold_comet = sorted(m.group(1) for m in re.finditer(
    r"^([a-z]{2}) & [a-z.]+\s*& \\textbf\{", _tbl, flags=re.M))
_rows_shown = sorted(m.group(1) for m in re.finditer(r"^([a-z]{2}) & [a-z.]+\s*&", _tbl, flags=re.M))
check(f"Table direction_full rows = expected language set ({len(_rows_shown)} rows)",
      _rows_shown == sorted(_direction_full_langs), f"got {_rows_shown}")
check(f"Table direction_full: COMET-bold rows {_bold_comet} = rows where COMET beats MetricX {_comet_wins}",
      _bold_comet == _comet_wins,
      "main.tex's hand-placed \\textbf markers (and the caption's win claim) need updating")

print("\n=== O. Table 8 (dir_sep)'s hand-placed COMET/CK23 bold markers match the data ===")
# Same class of bug as Section N, found by inspection 2026-09-12: six rows
# (en-kk, en-ta, en-tr, en-ja, en-is, en-lv) had NEITHER column bolded even
# though CK23 beats COMET in all six -- apparently missed because MetricX
# (not shown in this COMET-vs-CK23-only table) is the overall recommended
# metric for those cells, but the caption's rule is simply "bold = best
# between COMET and CK23", not "bold = overall recommended metric".
_sep_df = pd.read_csv(RESULTS / "direction_separated_correlations.csv")
_table8_cells = [
    ("fi", "x_to_en"), ("et", "x_to_en"), ("tr", "x_to_en"), ("kk", "x_to_en"),
    ("ta", "x_to_en"), ("ja", "x_to_en"), ("ha", "x_to_en"),
    ("fi", "en_to_x"), ("et", "en_to_x"), ("kk", "en_to_x"), ("ta", "en_to_x"),
    ("tr", "en_to_x"), ("ja", "en_to_x"), ("ha", "en_to_x"),
    ("lt", "x_to_en"), ("cs", "x_to_en"), ("pl", "x_to_en"), ("gu", "x_to_en"),
    ("ps", "x_to_en"), ("is", "x_to_en"),
    ("lt", "en_to_x"), ("cs", "en_to_x"), ("pl", "en_to_x"), ("gu", "en_to_x"),
    ("is", "en_to_x"), ("lv", "en_to_x"),
]
_t8_comet_wins = []
for lang, d in _table8_cells:
    _c = _sep_df[(_sep_df.lang == lang) & (_sep_df.direction == d) & (_sep_df.metric == "comet")].spearman_r.iloc[0]
    _k = _sep_df[(_sep_df.lang == lang) & (_sep_df.direction == d) & (_sep_df.metric == "cometkiwi23")].spearman_r.iloc[0]
    if _c > _k:
        _t8_comet_wins.append((lang, d))
check(f"Table 8: COMET beats CK23 for exactly (ha,x_to_en) and (is,x_to_en) (found {_t8_comet_wins})",
      set(_t8_comet_wins) == {("ha", "x_to_en"), ("is", "x_to_en")},
      f"got {_t8_comet_wins} -- main.tex's tab:dir_sep \\textbf markers need updating")

# ─────────────────────────────────────────────────────────────────────────────
print()
# ─────────────────────────────────────────────────────────────────────────────

if failures:
    print(f"FAILED ({len(failures)} failures):")
    for f in failures:
        print(f"  ✗ {f}")
    sys.exit(1)
else:
    total = sum(1 for line in open(__file__).readlines() if "check(" in line)
    print(f"All checks passed.")
    sys.exit(0)
