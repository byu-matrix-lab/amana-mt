"""Flag candidate hardcoded numeric claims in main.tex that should be macros.

Not a proof of wrongness — a triage list. Many hits are legitimate (citing
someone else's number, a bootstrap CI already computed inline, a table/section
reference). The point is surfacing every candidate so a human decides
macro-ize vs. leave, rather than relying on repeated manual greps.

Run from project root:
    python scripts/find_hardcoded_values.py
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN_TEX = ROOT / "latex" / "main.tex"

# Decimal number: optional sign, 0.XXX or X.XXX, 2-4 significant digits.
# Deliberately excludes bare integers (page/table/section numbers, years) and
# percentages already reported via macros elsewhere.
DECIMAL_RE = re.compile(r"(?<![A-Za-z{])([+-]?\d?\.\d{2,4})(?![A-Za-z}])")

# Integer fractions and "N of M" phrasing — win-counts, LOO cells, cell n's.
# Missed by DECIMAL_RE entirely since these have no decimal point (e.g. the
# "5 of 7 agglutinative languages" / "6/7 pairs" class of hardcode that
# slipped through several review passes before being caught by eye).
INT_FRACTION_RE = re.compile(r"\b(\d{1,4}\s*(?:/|of)\s*\d{1,4})\b")

# Lines/contexts to skip entirely — these are legitimately not data claims.
SKIP_LINE_PATTERNS = [
    r"^\\newcommand",
    r"^\\usepackage",
    r"^%",
    r"^\\label",
    r"\\citet\{",  # citation-year-adjacent lines handled by SKIP_IF_CITED_FACT below
]

# Substrings that mark a number as "someone else's finding," safe to leave
# hardcoded since it's not derived from our pipeline and has no macro source.
CITED_FACT_MARKERS = [
    "coherence Pearson",  # Mondshine et al.'s own reported numbers
]


def main():
    text = MAIN_TEX.read_text()
    lines = text.split("\n")

    hits = []
    for lineno, line in enumerate(lines, 1):
        if any(re.search(p, line) for p in SKIP_LINE_PATTERNS):
            continue
        is_cited_fact = any(marker in line for marker in CITED_FACT_MARKERS)

        for pattern, kind in [(DECIMAL_RE, "decimal"), (INT_FRACTION_RE, "int-fraction")]:
            for m in pattern.finditer(line):
                val = m.group(1)
                start = max(0, m.start() - 40)
                end = min(len(line), m.end() + 20)
                context = line[start:end].strip()
                hits.append({
                    "line": lineno,
                    "value": val,
                    "context": context,
                    "cited_fact": is_cited_fact,
                    "kind": kind,
                })

    print(f"Found {len(hits)} candidate hardcoded numeric literals in main.tex\n")
    for h in hits:
        flag = " [likely a cited external fact, review only]" if h["cited_fact"] else ""
        print(f"  L{h['line']:4d}  [{h['kind']:>12s}]  {h['value']:>10s}  ...{h['context']}...{flag}")

    non_cited = [h for h in hits if not h["cited_fact"]]
    print(f"\n{len(non_cited)} candidates NOT flagged as external citations — highest priority to macro-ize.")


if __name__ == "__main__":
    main()
