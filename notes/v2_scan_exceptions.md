# Reviewed exceptions: strict hardcoded-number scan of arxiv_submission/main.tex (2026-11-10)

Scanner: ~/projects/amanamt-followup/code_check/ssot/strict_scan.py. Every flagged
numeric or count token that is not a macro was reviewed. None is a data-derived result.

| Kind | Examples | Why it is allowed |
|---|---|---|
| Model / dataset names | MetricX-24, CK23, Kiwi-22, XCOMET-XL, Llama-3.1-8B, NLLB-200, FLORES-200, bleurt-large-512 | Identifiers |
| Years / editions | WMT20--23, 2017, 2021--22, WMT24 | Identifiers of test sets |
| Design constants | three annotation tiers, five neural metrics in the ensemble, five MQM languages, four tier-1a languages listed by name, n >= 6 LOO threshold, 95% CI, 1000 resamples, two directions, three label types | Fixed by the study design, not computed |
| List numbering | (1)-(5) in the evaluation protocol | Structural |
| Cited facts | "typically 5--15 pairs" per WMT edition; "200 ESA-annotated segments" (a proposed validation size) | Pre-existing, not our results |
| Narrative counts | "two years", "two correlated rows", "the last two", "all four" anomalies, "Two practical lessons", "all five" top performers named in the same sentence, "two low-resource languages" (km, ps after excluding ha) | Count objects named in the same sentence |
| Colour spec | red!60!black | LaTeX |

Table bold markers (table-bold category) are checked against the data by
scripts/assert_paper_invariants.py sections N and O.
