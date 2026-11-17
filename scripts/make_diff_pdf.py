"""Build arxiv_submission/diff_vs_published/diff.pdf: every change between the
published paper (latex/) and v2 (arxiv_submission/).

1. Inline \\input files and expand every macro to its literal value, each side
   with its own macro file. Changed numbers then diff like any other text.
2. latexdiff the two expanded sources. Text, captions and section titles are
   marked up; table bodies are not, because tabular markup does not compile here.
3. Banner every float whose (expanded) content is new or changed, and list the
   removed floats in a note at the top.

    module load texlive/2024
    python3 scripts/make_diff_pdf.py
"""
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_DIR, NEW_DIR = ROOT / "latex", ROOT / "arxiv_submission"
OUT = NEW_DIR / "diff_vs_published"


def macros(path):
    vals = {}
    for m in re.finditer(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}\s*(?:%.*)?$", path.read_text(), flags=re.M):
        vals[m.group(1)] = m.group(2)
    return vals


def expand(doc_dir):
    src = (doc_dir / "main.tex").read_text()
    for name in ("language_table_generated",):
        f = doc_dir / f"{name}.tex"
        if f.exists():
            src = src.replace(f"\\input{{{name}}}", f.read_text())
    vals = macros(doc_dir / "macros_generated.tex")
    src = src.replace("\\input{macros_generated}", "")
    pat = re.compile(r"\\(" + "|".join(sorted(map(re.escape, vals), key=len, reverse=True)) + r")(?![A-Za-z])")
    for _ in range(3):  # values can themselves contain macros
        src = pat.sub(lambda m: vals[m.group(1)], src)
    return src


FLOAT = re.compile(r"\\begin\{(table\*?|figure\*?|sidewaysfigure)\}(.*?)\\end\{\1\}", re.S)


def floats(src, doc_dir):
    """label -> (normalized float text, sha256 of every included image).
    Image bytes are compared too, so a changed figure with an unchanged caption
    is still flagged (lesson from the Mapudungun v2 diff)."""
    import hashlib
    out = {}
    for m in FLOAT.finditer(src):
        lab = re.search(r"\\label\{([^}]*)\}", m.group(2))
        if not lab:
            continue
        hashes = []
        for g in re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]*)\}", m.group(2)):
            f = Path(g) if Path(g).is_absolute() else doc_dir / g
            hashes.append(hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else "missing:" + g)
        text = re.sub(r"\\includegraphics(?:\[[^]]*\])?\{[^}]*\}", "", m.group(2))
        out[lab.group(1)] = (" ".join(text.split()), tuple(hashes))
    return out


def main():
    OUT.mkdir(exist_ok=True)
    for d in ("figures",):
        shutil.rmtree(OUT / d, ignore_errors=True)
        shutil.copytree(NEW_DIR / d, OUT / d)
    for f in ("acl.sty", "acl_natbib.bst", "custom.bib"):
        shutil.copy2(NEW_DIR / f, OUT / f)
    old, new = expand(OLD_DIR), expand(NEW_DIR)
    # figures removed in v2 are not in arxiv_submission/figures; point old includes at latex/figures
    old = old.replace("{figures/", "{" + str(OLD_DIR / "figures") + "/")
    (OUT / "old_expanded.tex").write_text(old)
    (OUT / "new_expanded.tex").write_text(new)
    diff = subprocess.run(
        ["latexdiff", "--math-markup=coarse",
         "--config=PICTUREENV=(?:picture|DIFnomarkup|tabular)[\\w\\d*@]*",
         str(OUT / "old_expanded.tex"), str(OUT / "new_expanded.tex")],
        capture_output=True, text=True, check=True).stdout

    fo, fn = floats(old, OLD_DIR), floats(new, NEW_DIR)
    status = {lab: ("NEW" if lab not in fo else "CHANGED") for lab, body in fn.items() if fo.get(lab) != body}
    removed = sorted(set(fo) - set(fn))
    for lab, st in status.items():
        i = diff.find(f"\\label{{{lab}}}")
        j = diff.rfind("\\caption{", 0, i)
        if i < 0 or j < 0:
            continue
        j += len("\\caption{")
        diff = diff[:j] + f"\\DIFbanner{{{st}}}" + diff[j:]
    preamble = ("\\usepackage{xcolor}\n\\newcommand{\\DIFbanner}[1]{\\colorbox{yellow}{\\textbf{#1 in v2:}}\\ }\n")
    diff = diff.replace("\\begin{document}", preamble + "\\begin{document}", 1)
    note = ("\\noindent\\fbox{\\parbox{\\columnwidth}{\\small\\textbf{Reading this diff.} Every change against the "
            "published WMT 2026 version: \\textcolor{red}{red struck-through} = removed, \\textcolor{blue}{blue "
            "underlined} = added. Numbers are shown literally on both sides, so changed values are marked too. "
            "Table bodies and figure images cannot be marked line by line; every new or changed table or figure "
            "carries a yellow banner in its caption."
            + (" Removed: " + ", ".join(r.replace("_", "\\_") for r in removed) + "." if removed else "")
            + "}}\n\n")
    diff = diff.replace("\\begin{abstract}", note + "\\begin{abstract}", 1)
    (OUT / "diff.tex").write_text(diff)
    print("banners:", status)
    print("removed floats:", removed)
    for step in (["pdflatex", "-interaction=nonstopmode", "diff.tex"], ["bibtex", "diff"],
                 ["pdflatex", "-interaction=nonstopmode", "diff.tex"], ["pdflatex", "-interaction=nonstopmode", "diff.tex"]):
        subprocess.run(step, cwd=OUT, capture_output=True, timeout=600)
    log = (OUT / "diff.log").read_text(errors="replace")
    errs = [l for l in log.splitlines() if l.startswith("!")]
    print("latex errors:", len(errs), errs[:5])
    print(re.findall(r"Output written on diff.pdf \(([^)]*)\)", log))


if __name__ == "__main__":
    main()
