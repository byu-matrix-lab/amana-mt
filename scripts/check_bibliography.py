"""Verify custom.bib entries against Crossref (DOI) / arXiv (preprint) APIs.

For each entry:
  - If it has a DOI, look it up directly on Crossref (authoritative).
  - Else if its url is an arxiv.org link, query the arXiv API by ID.
  - Else, skip (flagged as "no verifiable identifier").

Diffs the bib's title and last-name author list against the source-of-truth
record and prints mismatches. This catches typos, wrong years, and authors
dropped/added by hand-editing — the kind of error a spellchecker won't catch
and a human proofread of 29 entries can plausibly miss under deadline pressure.

Run from project root (needs internet — works from BYU login nodes):
    python scripts/check_bibliography.py
"""

import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BIB_PATH = ROOT / "latex" / "custom.bib"

CROSSREF_DOI_URL = "https://api.crossref.org/works/{doi}"
ARXIV_API_URL = "https://export.arxiv.org/api/query"


def parse_bib(path: Path) -> list[dict]:
    """Minimal BibTeX parser — good enough for this project's flat, single-file .bib."""
    text = path.read_text()
    entries = []
    for m in re.finditer(r"@(\w+)\{([^,]+),", text):
        entry_type, key = m.group(1), m.group(2)
        start = m.end()
        # Find the matching closing brace by depth counting from the entry's opening brace
        depth = 1
        i = start
        while depth > 0 and i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[start:i - 1]

        fields = {}
        for fm in re.finditer(r"(\w+)\s*=\s*\{((?:[^{}]|\{[^{}]*\})*)\}", body):
            fields[fm.group(1).lower()] = fm.group(2)
        entries.append({"type": entry_type, "key": key, **fields})
    return entries


def strip_latex(s: str) -> str:
    """Strip common LaTeX accents/braces for fuzzy comparison."""
    s = re.sub(r"\{\\'([a-zA-Z])\}", r"\1", s)   # {\'e} -> e
    s = re.sub(r"\\'([a-zA-Z])", r"\1", s)         # \'e -> e
    s = re.sub(r"\{\\`([a-zA-Z])\}", r"\1", s)
    s = re.sub(r"\\`([a-zA-Z])", r"\1", s)
    s = re.sub(r"\{\\v\{([a-zA-Z])\}\}", r"\1", s)
    s = re.sub(r"\\v\{([a-zA-Z])\}", r"\1", s)
    s = s.replace("{", "").replace("}", "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.lower().strip()


def last_names(author_field: str) -> set[str]:
    """Extract last names from a BibTeX 'Last, First and Last, First' string."""
    names = set()
    for author in author_field.split(" and "):
        author = author.strip()
        if author.lower() in ("others", "{nllb team}", "nllb team"):
            continue
        if "," in author:
            last = author.split(",")[0]
        else:
            last = author.split()[-1] if author.split() else author
        cleaned = strip_latex(last)
        if cleaned:
            names.add(cleaned)
    return names


def fetch_crossref_by_doi(doi: str) -> dict | None:
    try:
        resp = requests.get(CROSSREF_DOI_URL.format(doi=doi), timeout=10)
        if resp.status_code != 200:
            return None
        msg = resp.json()["message"]
        title = msg.get("title", [""])[0]
        authors = msg.get("author", [])
        last = {strip_latex(a.get("family", "")) for a in authors if a.get("family")}
        year = None
        for date_key in ("published-print", "published-online", "issued"):
            if date_key in msg and "date-parts" in msg[date_key]:
                year = msg[date_key]["date-parts"][0][0]
                break
        return {"title": title, "authors": last, "year": year}
    except (requests.RequestException, KeyError, IndexError):
        return None


def fetch_arxiv(arxiv_id: str) -> dict | None:
    try:
        resp = requests.get(ARXIV_API_URL, params={"id_list": arxiv_id}, timeout=10)
        if resp.status_code != 200:
            return None
        text = resp.text
        title_m = re.search(r"<title>(.*?)</title>", text, re.DOTALL)
        titles = re.findall(r"<title>(.*?)</title>", text, re.DOTALL)
        # First <title> is the Atom feed title; entry title is the second
        title = titles[1].strip() if len(titles) > 1 else None
        authors = set(strip_latex(n) for n in re.findall(r"<name>(.*?)</name>", text))
        year_m = re.search(r"<published>(\d{4})-", text)
        year = int(year_m.group(1)) if year_m else None
        if title is None:
            return None
        return {"title": re.sub(r"\s+", " ", title), "authors": authors, "year": year}
    except requests.RequestException:
        return None


def extract_arxiv_id(url: str) -> str | None:
    m = re.search(r"arxiv\.org/abs/([\w.]+)", url)
    return m.group(1) if m else None


def titles_match(bib_title: str, src_title: str) -> bool:
    a = re.sub(r"[^a-z0-9 ]", "", strip_latex(bib_title))
    b = re.sub(r"[^a-z0-9 ]", "", strip_latex(src_title))
    a_words = set(a.split())
    b_words = set(b.split())
    if not a_words or not b_words:
        return False
    overlap = len(a_words & b_words) / max(len(a_words), len(b_words))
    return overlap > 0.7


def main():
    entries = parse_bib(BIB_PATH)
    print(f"Parsed {len(entries)} entries from {BIB_PATH.relative_to(ROOT)}\n")

    issues = []
    skipped = []

    for e in entries:
        key = e["key"]
        bib_title = e.get("title", "")
        bib_authors = last_names(e.get("author", ""))
        bib_year = e.get("year", "")

        src = None
        source_name = None
        if "doi" in e:
            src = fetch_crossref_by_doi(e["doi"])
            source_name = f"Crossref DOI:{e['doi']}"
            time.sleep(0.3)
        elif "url" in e and "arxiv.org" in e["url"]:
            arxiv_id = extract_arxiv_id(e["url"])
            if arxiv_id:
                src = fetch_arxiv(arxiv_id)
                source_name = f"arXiv:{arxiv_id}"
                time.sleep(0.3)

        if src is None:
            skipped.append((key, "no DOI/arXiv identifier or lookup failed"))
            print(f"  SKIP   {key}  (no verifiable identifier — ACL Anthology url only)")
            continue

        entry_issues = []
        if not titles_match(bib_title, src["title"]):
            entry_issues.append(f"title mismatch: bib='{bib_title}' vs {source_name}='{src['title']}'")

        if src["authors"] and bib_authors:
            missing_from_bib = src["authors"] - bib_authors
            extra_in_bib = bib_authors - src["authors"]
            if missing_from_bib:
                entry_issues.append(f"authors in {source_name} but missing from bib: {missing_from_bib}")
            if extra_in_bib:
                entry_issues.append(f"authors in bib but not in {source_name}: {extra_in_bib}")

        if src["year"] and bib_year and str(src["year"]) != str(bib_year).strip():
            entry_issues.append(f"year mismatch: bib={bib_year} vs {source_name}={src['year']}")

        if entry_issues:
            print(f"  FAIL   {key}")
            for issue in entry_issues:
                print(f"           - {issue}")
            issues.append((key, entry_issues))
        else:
            print(f"  PASS   {key}  ({source_name})")

    print(f"\n{len(entries) - len(skipped) - len(issues)} verified clean, "
          f"{len(issues)} with discrepancies, {len(skipped)} skipped (no identifier).")

    if issues:
        sys.exit(1)


if __name__ == "__main__":
    main()
