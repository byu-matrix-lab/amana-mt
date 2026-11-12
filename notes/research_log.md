# Research Log — Multilingual MQM Benchmark

## 2026-09-11 (Session — dash cleanup, page-1 teaser figure, build pipeline, SLURM speedup)

### Dash style cleanup
User dislikes em dashes and en dashes misused as em dashes. Found and fixed every " -- " (spaced double-hyphen rendering as an en-dash) used as a parenthetical/aside in `main.tex`, both the two I'd introduced today (EMET footnote, Hebrew paragraph) and four pre-existing ones (the agglutinative/fusional gap bullets, year-stratification paragraph, protocol-confound paragraph), rewritten using commas/parentheses instead. Left the legitimate uses alone: numeric ranges (`2017--2022`), compound terms (`metric--human`), and table "no data" placeholders (`--`).

### New page-1 teaser figure
User asked whether there's enough visual content and specifically wanted an attention-grabbing figure/table near the top. Added `plot_direction_morphology_teaser()` to `scripts/make_presentation_plots.py`: a compact grouped bar chart (en->X vs. X->en COMET rho, split by isolating/agglutinative/fusional) with the eta^2_dir vs. eta^2_morph annotation, placed as `\begin{figure}[t]` right at the top of the Introduction (page 1). Per the user's explicit instruction, it reads every value directly from `results/paper_stats.json` (the exact `DirMorphCOMET*`/`EtaSq*` keys `generate_paper_stats.py` already writes for Table 2) rather than recomputing anything independently, the same pattern already established in `plot_tier_bar()`.

### Removed SSOT-noncompliant dead code
While auditing "should plots draw from SSOT," found `plot_score_discrimination()` (already unused since the Hebrew retraction removed its LaTeX figure) was independently reconstructing a `he_<system>_<globalSegId>` segment-ID join against `surface_similarity.csv`, the exact same stale-join anti-pattern that caused this session's earlier Cohen's-d NaN bug, just never fixed because the function was dead code by that point. Deleted the function entirely rather than leave a landmine for a future session that might resurrect it.

### Regenerated kiwi_scatter as a neutral figure
Per earlier discussion, restored `presentation_kiwi23_vs_comet.pdf` (CK23 vs. COMET scatter, all languages) as a legitimate general figure now that the Hebrew-specific "sole outlier" annotation and bold styling are removed. Verified the new caption's claim ("reference-free QE holds a modest overall edge") against the data before writing it: mean(CK23-COMET) = +0.016, CK23 wins 19/26 languages, true. Re-added the LaTeX figure block in \S\ref{sec:per_lang}.

### New build pipeline: `scripts/build_paper.sh`
Ties the whole pipeline into one command: `generate_paper_stats.py`, then `render_macros.py`, `make_presentation_plots.py`, `assert_paper_invariants.py`, and `pdflatex` x2, failing loudly on the first error rather than silently compiling against stale macros or stale figure PDFs. This is now the only sanctioned way to compile; running `pdflatex` directly on a stale `results/` state was exactly the kind of drift the SSOT discipline exists to prevent.

### SLURM speedup for generate_paper_stats.py
Running the full build hung: `generate_paper_stats.py` (CPU-bound, bootstrap CIs) sat at 98% CPU for 12+ minutes on the login node without finishing, versus ~1-2 minutes in every earlier run today. Diagnosed with `nproc` (1 usable core) and `uptime` (load average 11+, 60 concurrent users): pure resource contention on an oversubscribed shared login node, not a bug in anything edited this session. Killed it and submitted `scripts/slurm/run_generate_paper_stats.sh` (new: CPU-only, 4 cores, 32G, 30 min limit) instead; completed in 93 seconds with identical output (eta_dir=0.309, 566 entries) to what the stalled login-node run would eventually have produced. Documented this in `build_paper.sh` itself so the next session doesn't have to rediscover it.

### Major bug found: latex/figures/ was silently stale for over a month
User reported "the funky Hebrew dot is still in the graph" and "the new graph didn't work." Investigated by actually rendering the compiled PDF pages as images (installed `pypdfium2` via pip, since no `pdftoppm`/`imagemagick`/`pdftotext` were available and this session's Read tool can view images directly, a new capability worth remembering). Findings:
- The teaser figure's box was empty, showing the literal path string `figures/presentation_direction_morphology_teaser.pdf` as placeholder text: the classic LaTeX behavior when `\includegraphics` can't find the target file.
- Checked `latex/figures/` vs. `results/plots/`: **every single figure differs** (sha256 mismatch on all of them). `latex/figures/` held PDFs dated 2026-08-07, over a month stale, while `make_presentation_plots.py` has only ever written to `results/plots/`. Nothing in this whole project's history copied one into the other.
- This means every "verify the figure is fixed" check earlier in today's session was checking the wrong file: `results/plots/presentation_kiwi23_vs_comet.pdf` was correctly regenerated (Hebrew annotation removed, caption fixed), but the actual **compiled PDF was still embedding the August version with the retracted Hebrew-outlier annotation still visible**, because `pdflatex` reads from `latex/figures/`, not `results/plots/`.
- `build_paper.sh`'s own header comment already *claimed* to prevent exactly this kind of stale-figure drift, but the script never actually copied the files across, an oversight caught only by testing the real compiled output, not by reading the script's own comments.

Fixed: `cp results/plots/*.pdf latex/figures/` now runs as an explicit step in `build_paper.sh` between plot generation and `pdflatex`. Added invariant section L to `assert_paper_invariants.py`: hashes every `figures/*.pdf` main.tex references against its `results/plots/` source, so a manual `pdflatex` run that bypasses `build_paper.sh` still gets caught rather than silently compiling stale figures. (Note: `hashlib.md5` is unavailable in this environment's OpenSSL build, FIPS-restricted; used `sha256` instead.)

Re-synced, recompiled, and re-verified all four embedded figures by actually rendering the compiled PDF pages to images and reading them: teaser figure now displays correctly on page 1 next to the abstract, and the kiwi_scatter figure now shows the correct neutral version with Hebrew/Spanish visibly below the diagonal and the caption accurately describing them as outliers (see next entry).

### Table 2 fixes (fit + bold ambiguity)
User: "table 2 looks like it could fit in one column" and "confused about what is bold in table 2." Rendered the compiled page and confirmed both: the table used `table*` (two-column span) but only filled about half that width, and two unrelated things were bold (the X-to-en agglutinative COMET cell, explained in the caption; and eta^2_cell, never explained). Converted `table*` to `table` (single column); this initially overflowed by 25pt with the full `[lo, hi]` CI brackets at `\small`, so switched to `\footnotesize` with tighter `\tabcolsep` and `\scriptsize` CI brackets set flush against the value (no space) rather than dropping the CI data or falsifying a "see Table 4" pointer (checked first: Table 4's CIs are on a different quantity, win-fraction, not the same as these per-cell mean-rho CIs, so that pointer would have been wrong). Removed the bold from eta^2_cell entirely (it had no comparative meaning) and rewrote the caption to state explicitly that only the X-to-en agglutinative cell is bold and why. Verified by rendering the compiled page: no overfull hbox, single bold value, caption unambiguous.

### Kiwi-scatter caption accuracy fix
Verifying the caption I wrote earlier this session ("no single language is a substantial outlier") against the actual data: false. He and es are the two largest deviations from the diagonal in the entire 26-language dataset (-0.173 and -0.142, both more than double the third-largest at 0.085), just in COMET's favor now instead of CK23's. Added a new SSOT macro `GapEsKiwiComet` (matching the existing `GapHeKiwiComet` pattern) and rewrote the caption to state this plainly without speculating a cause, consistent with having already withdrawn the OOD-coverage hypothesis in section 5.2.

### Final state
Full pipeline clean end to end: `assert_paper_invariants.py` all pass (12 sections, including two new ones added this session: undefined-macro scan and figure-staleness check), `find_hardcoded_values.py` 0 candidates, `pdflatex` x2 compiles clean (17 pages, zero undefined refs/citations/reruns-needed, zero overfull hboxes), 4 figures (page-1 teaser + heatmap + tier bar + kiwi_scatter) and 7 tables, all verified by actually rendering and reading the compiled pages, not just checking exit codes.

## 2026-09-11 (Session — full external validation + first real compile)

### External baseline validation, extended to all four fixed metrics x both languages
User asked "any other baselines like that we should check?" after the single Hebrew/COMET-22 validation earlier. Extended it: pulled `wmt24/metric-scores/en-es/` (Spanish, the other language affected by the same bug) plus BLEURT-20, xCOMET, and MetricX segment-score files for both he-en (wmt23) and en-es (wmt24) from the official `mt-metrics-eval` archive, and compared system-level means against our corrected checkpoints:

| lang | metric | n systems | Pearson r | Spearman r |
|---|---|---|---|---|
| he | COMET-22 | 12 | 0.977 | 0.972 |
| he | BLEURT-20 | 12 | 0.954 | 0.923 |
| he | xCOMET | 12 | 0.979 | 0.986 |
| he | MetricX-23 | 12 | 0.894 | 0.888 |
| es | COMET-22 | 14 | 0.981 | 0.868 |
| es | BLEURT-20 | 14 | 0.937 | 0.807 |
| es | xCOMET | 14 | 0.981 | 0.943 |
| es | MetricX-24 | 14 | 0.987 | 0.934 |

All eight checks (every metric that was actually buggy, for every language that was actually affected) show strong-to-decisive agreement with official WMT baselines. This is airtight external validation of the reference-omission fix, not just internal self-consistency. `/tmp/mtme` (the ~900MB extracted archive) deleted after use both times.

### First real pdflatex compile of the whole session
User pointed out `texlive/2024` is available as an environment module (`module load texlive/2024`) — no LaTeX compiler had been available before this, so all of today's earlier edits were only structurally verified (braces, macro-name checks), never actually compiled. Loaded the module, ran a full `pdflatex` x2 pass (`main.bbl` already existed and no citations changed, so no `bibtex` rerun needed). Compiled clean to a 16-page PDF on the second attempt.

**Found and fixed a real, pre-existing bug the compile caught that predates this session's Hebrew work**: Table 1's caption referenced `\TierGEMBAMedRho`, a macro `generate_paper_stats.py` never generates (confirmed via grep — no such key anywhere in the SSOT script). The sentence was also internally self-contradictory: it said GEMBA is *excluded* from the Med tier, then cited a Med-tier rho for it in the same breath — clearly leftover text from an earlier paper draft that survived a restructuring. Removed the dangling parenthetical. This is exactly the class of bug `assert_paper_invariants.py` was blind to: it verifies macros that exist have correct values, but never checked that every macro *referenced in the prose* actually exists.

**Added a permanent invariant (`scripts/assert_paper_invariants.py`, section K)**: regex-scans `main.tex` for CamelCase macro usages and checks each one is defined somewhere (`macros_generated.tex`, `language_table_generated.tex`, or inline in `main.tex` itself), filtering out a hardcoded allowlist of ordinary LaTeX control words. Confirmed it currently reports 0 undefined macros (the GEMBA one was the only offender) and would have caught this bug immediately without needing a LaTeX compiler at all.

### Baseline-validation numbers wired through the SSOT, sentence added to the paper
Per standing policy (every quantity in the paper traces to code + SSOT JSON, never hand-typed), the 8-check external-validation table above couldn't just be quoted in the research log and dropped into the paper as literals. Created `results/wmt_baseline_validation.csv` (the 8 rows: lang, testset, metric, official submission name, n_systems, pearson_r, spearman_r, source path) as the new SSOT input, added a section to `generate_paper_stats.py` that reads it and emits `BaselineValNChecks`/`BaselineValMinPearson`/`BaselineValMinSpearman` (worst-case across all 8 checks, so the claim is conservative), and added one sentence to §sec:qe_ref citing those macros: "we validated the fix externally... Pearson r≥0.894 and Spearman r≥0.807 across all 8 checks." Reran the full pipeline (`generate_paper_stats.py` → `render_macros.py` → `assert_paper_invariants.py`, all pass, 566 macros now) and recompiled — clean, 17 pages, zero warnings about undefined refs/citations/reruns needed.

Final state: PDF compiles clean under `texlive/2024`, `find_hardcoded_values.py` reports 0 candidates, `assert_paper_invariants.py` passes all checks including the new macro-existence one. This closes out every item from both `advisor_email.md` and `wmt_review.md`, plus the Hebrew retraction and its downstream validation.

## 2026-09-11 (Session — Advisor-flagged Hebrew/Ukrainian anomalies + WMT26 camera-ready)

### Context
WMT26 camera-ready deadline is today (2026-09-11, AoE). Two open threads: Dr. Ringger's advisor-review email (`notes/advisor_email.md`) flagging suspicious near-zero Ukrainian correlations and an unexplained Hebrew COMET/BLEURT anomaly, and the WMT26 reviewer packet (`notes/wmt_review.md`).

### Follow-up closures (later same session)
- **Validated corrected Hebrew COMET-22 against the official WMT23 baseline** (Eric's suggested "cheap check"). Downloaded `google-research/mt-metrics-eval`'s WMT23 archive (current URL is `https://data.statmt.org/wmt26/mt-metrics-eval-v2.tgz`; the URL in its own README is stale/403s) and extracted `wmt23/metric-scores/he-en/COMET-refA.seg.score`, the actual WMT23-submitted COMET-22 scores. System-level means (12 systems) correlate with our corrected `scores_comet.csv` he rows at Pearson r=0.977, Spearman r=0.972 — a small systematic offset (~0.05-0.06 lower across the board, likely a COMET checkpoint/config difference) but near-perfect rank agreement. This is decisive external validation that the reference-fix is correct, not just internally self-consistent.
- **Added the Tier-2 segment-ID verification to the paper text** (`latex/main.tex` §results, the "Tier~2 near-zero" paragraph): explicitly states that the FLORES-based segment_id sharing across all 7 Tier-2 languages was checked and ruled out as a repeat of the he-en/en-es pipeline bug, via independent rebuild-and-rejoin-by-language. Kept the existing careful "we draw no typological conclusion from this" language intact — this addition only strengthens the "not a bug" claim, doesn't newly claim the LLM-judge-unreliability mechanism (which remains an unproven hypothesis).
- Cleaned up the ~900MB mt-metrics-eval tarball from `/tmp` after use.

### Bugs found and fixed
1. **Hebrew (he-en, wmt23) and Spanish (en-es, wmt24) reference-omission + segment_id-scheme bug.** Both language pairs load via the span-fallback loader (`load_wmt_mqm_spans`), the only path affected. Root cause: reference text wasn't being attached correctly, and segment_id collisions/scheme mismatches broke the pipeline's `--analysis-only` positional-alignment merge. Fixed generically in `scripts/generate_paper_stats.py` (`_SPAN_LANG_SPECS` / `_build_span_lang_correct_rows()`), which bypasses the fragile merge and recomputes both languages directly from corrected span data + real sacreBLEU references. Verified: Spanish's 9 checkpoint CSVs regenerated via SLURM (job 13649745 — note job 13649555 was a red herring, it was *cancelled*, not completed; a wait-loop that only checks "job left the queue" cannot distinguish cancellation from completion, must use `sacct` for real status).
2. **Second-order bug: `correlations.csv` on disk was never updated.** The fix above patched `corr_df`/`da_df` only in-memory. `build_corrected_lang_dir_rho()` — used by the paper's *central* direction×morphology 2×3 analysis, the mixed-effects model (reviewer-requested robustness check), DiD, and the decision-procedure table — re-reads `correlations.csv` fresh from disk, so all of that silently kept using the pre-fix broken he/es numbers even after the in-memory fix looked complete and all invariants passed. Fixed by writing the corrected he/es rows back into `correlations.csv` on disk too. This changed the headline numbers again: η²_dir 0.269→0.309, η²_morph 0.143→0.073, η²_interact 0.587→0.618, DiD 0.060→0.036. Lesson: when a "fix" touches an in-memory dataframe, grep for every other place that re-reads the same file from disk before declaring done.
3. **Third-order bug: Hebrew discrimination/Cohen's-d analysis used a stale, mismatched segment_id join.** `surface_similarity.csv` (from standalone `analyze_surface_similarity.py`) builds its own `he_<system>_<globalSegId>` segment_id, which no longer matches `scores_comet.csv`'s post-fix segment_id scheme — the merge silently produced 0 rows, so Hebrew's Cohen's d rendered as `nan`. Fixed by rebuilding the Hebrew quality-bucketing directly from the same corrected span+ref-lookup path as the main fix, rather than trusting the mismatched CSV join.

### Investigated, not bugs (verified, no fix needed)
- **Ukrainian**: independently reconfirmed near-zero correlation is a genuine domain confound (uk-en 2022 is conversational "other" domain, not news), not a pipeline bug.
- **is-en / ha-en**: advisor asked for the same segment-ID spot-check applied to Ukrainian. Checked — segment_id is fully unique for both (19,741/19,741 and 23,983/23,983), and correlations are weak-but-real (spearman 0.10–0.52, pairwise_acc 0.53–0.68, sensible metric ordering), not coin-flip. "Annotation noise" is the correct characterization, not a bug.
- **Tier-2 synthetic-MQM languages (am, lo, my, sw, ht, th, ka)**: all show uniformly weak correlation across every metric including reference-based ones. Rebuilt each language's quality scores directly from the raw synthetic-MQM JSONL cache and re-joined by segment_id+lang — matched the pipeline's reported values to 6 decimal places. Despite the FLORES-based segment_id scheme being a latent landmine (identical `flores_devtest_XXXX` ids shared across all 7 Tier-2 languages, no `lang` in the join key), current results are correctly aligned. The near-zero pattern is a genuine finding: the local LLM judge (Llama-3.1-8B) can't produce reliable quality judgments for these low-resource/non-Latin-script languages.
- **Alternate Hebrew reference**: advisor asked to check whether an alternate he-en reference exists, since Limitations claims none is available. Confirmed WMT23 does publish a second reference (`refB`, 1910 lines, genuinely distinct human translation, cached locally) — the paper's Limitations claim is currently **false** and needs correcting (not yet done — pending, see below).

### WMT26 reviewer packet — already addressed in a prior session (confirmed, not re-done)
Checked `notes/wmt_review.md` against current `latex/main.tex`: the Hausa fusional/agglutinative Table 6 vs. Table 7 inconsistency (Reviewer 2), the linear mixed-effects robustness model with language random intercept (Reviewer 2 Q1/Q2/Q6), the practical decision-procedure/recipe (Reviewer 1), the pivot→X↔Y terminology fix (Reviewer 1), and the year-stratification robustness check (Reviewer 3) are all already present and SSOT-compliant. Re-ran the full pipeline after today's fixes to confirm these still hold with corrected data — they do (all `assert_paper_invariants.py` checks pass).

### Big open item — NOT resolved, needs a decision
The corrected data **reverses** the paper's "reference-coverage hypothesis" (Hebrew as the sole case where OOD training coverage makes reference-free CK23 beat reference-based COMET). With the fix: COMET now beats CK23 for Hebrew (0.713 vs 0.540 spearman), and COMET's discrimination (Cohen's d = 1.98) is now *better* than CK23's (1.27) — the opposite of the original claim. This affects the abstract, a full results subsection, the Pashto control comparison, the Limitations sentence about missing multi-reference data, and the discrimination-collapse appendix figure. Discussed two options with the user (cut to a null result vs. reframe as a case study in pipeline fragility) — **decision deferred, revisit before submission.**

### Hebrew reference-coverage hypothesis retracted (decision made, executed same session)
Discussed the open item above with the user. Considered reframing as a "case study in pipeline fragility" but the user pushed back — correctly, on reflection: a bug-fix narrative isn't a generalizable finding for readers the way "always stratify by year" is, and it risked reading as process navel-gazing under deadline pressure. Went with the null-result cut instead. Edited `latex/main.tex`:
- Abstract: removed the Hebrew/Pashto OOD-coverage sentence.
- EMET footnote: re-justified the name around the paper's actual throughline (anomalies traced to verifiable causes, not language properties) instead of the Hebrew finding specifically.
- Removed Contributions bullet 5 ("Reference coverage, not script type...").
- Rewrote the §per_lang Hebrew paragraph: COMET is now Hebrew's *best* metric (beats xCOMET, MetricX, CK23, Kiwi-22, BERTScore); one sentence acknowledges the earlier version reported the reverse and traces it to the fixed pipeline bug.
- Removed the `fig:kiwi_scatter` figure (Hebrew-outlier scatter plot) and its Results-section lead-in sentence.
- Removed the Hebrew-vs-Spanish "reference-coverage mismatch" comparison clause.
- Rewrote §sec:qe_ref (renamed "No Reference-Coverage Anomaly for Abjad Scripts") to state the retraction plainly, kept the `\label{sec:qe_ref}` so nothing else breaks.
- Removed the OOD-coverage paragraph and decision-procedure item 5 ("Unknown reference coverage: default to reference-free QE") from §discussion.
- Removed "confirm the abjad QE-advantage on Arabic and Urdu" from Future Work, and a leftover "Arabic... direct generalization test of the Hebrew QE-advantage finding" clause in Limitations.
- Fixed the Limitations sentence: was falsely claiming no alternate he-en reference exists (refuted by today's refB discovery); now correctly discloses that only refA was used and refB exists but wasn't.
- Removed the Appendix "Score Discrimination Collapse: Hebrew" figure and subsection entirely — its Cohen's d values reversed (COMET 1.98 now beats Kiwi's 1.27, the opposite of the original "collapse" story) and the figure no longer illustrates anything paper-relevant.
- Added `\label{sec:limitations}` to the previously-unlabeled `\section*{Limitations}` (was about to be dangling-referenced), then switched to plain-text "(see Limitations)" instead since `\ref` on a starred/unnumbered section is unreliable across LaTeX classes — matches an existing convention already used elsewhere in the paper.
- Verified via `scripts/find_hardcoded_values.py` (0 candidates) and a custom label/ref audit (only one pre-existing, unrelated dangling ref: `tab:languages`, which lives in a separately-`\input`-ed generated file and was never actually missing).
- Also caught mid-edit: `results/abjad_score_distributions.csv` had been regenerated (by `analyze_abjad_mechanism.py`) with corrected data at some point this session outside of what's visible in this log/conversation, but `generate_paper_stats.py` hadn't been rerun since — `HeFullMeanComet` was stale at 0.423 (the literal number from Eric's original email) when the underlying CSV already said 0.790. Reran the full pipeline to pick it up; all these macros are now unused in the text anyway after the rewrite above, but the SSOT itself is correct.
- Full pipeline (`generate_paper_stats.py` → `render_macros.py` → `assert_paper_invariants.py`) reruns clean after all of the above.
- **Not done**: LaTeX compile check — no `pdflatex`/`xelatex` available on this machine; only structural checks (brace balance, label/ref audit, hardcoded-literal scan) were possible. Compile on Overleaf before final submission.

### Pipeline state at end of session
`results/correlations.csv`, `results/hebrew_discrimination.csv`, `results/paper_stats.json`, and `latex/macros_generated.tex` are all regenerated and consistent; `scripts/assert_paper_invariants.py` passes all checks (DiD baseline updated to 0.036 to match corrected data).

## 2026-08-08 (Session — Post-deadline: Tier-2 contamination fix + SSOT + rewrite for next venue)

### Summary
Discovered critical data contamination: Tier-2 synthetic MQM languages (sw, ht, lo, th, my, am, ka) were included in Table 2 en→X cell means. This inverted the paper's headline claim: η²_dir was 0.039 (contaminated) → 0.387 (correct), η²_morph 0.088 → 0.027, η²_cell 0.872 → 0.586. The new spine: **direction dominates (η²=0.387); morphological type barely matters (η²=0.027)**. Missed WMT-2026 deadline; targeting EACL 2027 (2026-08-03 deadline, already past) → COLING/NAACL 2027 (2026-10-12).

Also discovered: Ridge regression script (`build_metric_reliability_predictor.py`) was running on all 33 languages, not 26 Tier-1 as claimed in the paper. Fixed with TIER2_LANGS filter. Corrected Pearson r: CK23 0.56→0.47, CK 0.61→0.56.

### Changes made
- **SSOT**: `recompute_dir_morph_table.py` now writes `latex/macros_generated.tex` (all DirMorph, EtaSq, DirMetric macros). Run with `/fslhome/it238/.conda/envs/my_env/bin/python scripts/recompute_dir_morph_table.py` from project root.
- **Tier-2 filter**: Added `TIER2_LANGS` constant and filter to both `recompute_dir_morph_table.py` and `build_metric_reliability_predictor.py`.
- **Ridge rerun (n=26 Tier-1)**: CK23 LOLO Pearson r=0.469, CK r=0.558. Paper updated accordingly.
- **Year-stratified verified**: de/ru/zh per-year values confirmed correct against tier_anomaly.csv and simpsons_summary.csv.
- **Per-cell language lists (Tier-1 only)**:
  - en→X agglutinative n=7: et, fi, ha, ja, kk, ta, tr
  - en→X fusional n=9: de, es, lv, ru, cs, gu, is, lt, pl
  - X→en agglutinative n=7: et, fi, ha, ja, kk, ta, tr (direction-separated)
  - X→en fusional n=8: he, ps, uk, cs, gu, is, lt, pl (direction-separated)
  - X→en isolating n=2: km, zh
  - pivot fusional n=5: bn, fr, hi, xh, zu
  - en→X isolating: **empty** (all isolating langs are Tier-2 or X→en only)

### Key corrected values
- η²_dir=0.387, η²_morph=0.027, η²_cell=0.586
- en→X agglutin=0.628 [0.522,0.709] n=7, en→X fusional=0.587 [0.455,0.689] n=9
- X→en agglutin=0.384 [0.230,0.518] n=7, X→en fusional=0.257 [0.148,0.358] n=8
- DiD (fusional gap − agglutinative gap) = 0.330 − 0.244 = 0.086 (small; direction effect is largely constant across morphological types)

### Rewrite summary (main.tex)
- Abstract sentence 3: new spine (direction dominates)
- Contribution bullet 1: retitled "Direction dominates; morphological type barely matters"
- §3.3 framing: removed "failure of either factor alone" language
- §4.4: hardcoded gaps updated (+0.073→+0.244, +0.28→+0.33, DiD 0.21→0.086)
- §5.3: direction dominates framing
- §6: fixed "neither factor alone" + "0.21" DiD
- Limitations: added empty en→X isolating cell note
- Ridge r-values corrected

### What's still TODO for next submission
- Title change: consider "Direction, Not Typology: What Actually Predicts Which MT Metric to Trust"
- Ridge figure (Appendix) needs regenerating with Tier-1-only coefficients
- Consider whether §4.5 opening (η²_cell framing) needs further adjustment
- Year-stratified macros still marked "manual" — add a generating script reading tier_anomaly.csv

## 2026-08-08 (Session cont'd — Infrastructure build: tier refactor, invariant checks, bib audit, recompile)

### Summary
Finished the infrastructure hardening plan from earlier in this session (Opus 5's "shape that actually works" prescription). Title changed to "Direction, Not Typology, Predicts Which MT Metric to Trust"; Ridge appendix figure cut entirely (was built from n=33, wrong). Built four pieces of tooling so future edits can't silently reintroduce Tier-2 contamination or drift from the SSOT:

1. **Tier refactor**: `TIER2_LANGS` moved to `src/mqmbench/analysis/correlation.py` as the canonical definition; `recompute_dir_morph_table.py` and `build_metric_reliability_predictor.py` now import it instead of keeping local copies. `generate_macros.py` no longer writes DirMorph/EtaSq/DirMetric/year-stratified macros (removed ~90 lines of now-dead code, including the `morph_of`/`MORPHOLOGY` dict and `dm_df` load) — those are exclusively owned by `latex/macros_generated.tex` via the two scripts below, eliminating the SSOT conflict where re-running `generate_macros.py` would silently overwrite corrected values with stale ones.

2. **`scripts/assert_paper_invariants.py`**: 53 checks — TIER2_LANGS excluded from every Tier-1 aggregate, no language double-counted across direction/morphology groups, cell n's match claimed values (en→X agglutin=7, fusional=9, X→en isolating=2/agglutin=7/fusional=8, pivot=5), every macro in macros_generated.tex matches a fresh recomputation from the CSVs, Table 1 filters synthetic_mqm, direction assignments are internally consistent, and the four main-claim invariants hold (η²_dir > η²_morph, en→X > X→en for both morph types, DiD≈0.086, Ridge n=26/r=0.469,0.558/accuracy=2/26). All pass.

3. **`scripts/generate_yearstrat_macros.py`**: replaces the hardcoded "manual" RuWmtOneRho/DeWmtTwoZeroRho macros with values read live from `tier_anomaly.csv` (confirmed identical to the old hardcoded values). Also discovered and fixed three macros (`\DeEnKiwiRho`, `\DeEnCOMETRho`, `\DeEnMetricXRho`) that were referenced in main.tex but never defined anywhere — the held-out de-en validation numbers from session 26 (2026-07-08) were in the paper text/log but never made it into a macro file, so every prior compile after the SSOT split was silently broken (`pdflatex` errored with "Undefined control sequence" until this fix). Recomputed from `scores_de_en.csv` directly: COMET=0.383, CK23=0.414, MetricX=0.389 — exact match to the session-26 values, confirming no drift.

4. **`scripts/check_bibliography.py`**: cross-checks all 29 `custom.bib` entries with DOIs or arXiv IDs against Crossref/arXiv APIs (login node has internet access). Found one real bug: `zouhar2024domain`'s DOI (`10.18653/v1/2024.acl-short.44`) pointed to an unrelated debate-evaluation paper — off-by-one in the ACL Anthology ID, correct is `.45`. Fixed. Also flagged (but left alone, verified correct) a Crossref metadata quirk where `papineni2002bleu`'s registered `published-print` date is 2001 despite the proceedings being ACL '02 — the paper's `year=2002` is right; Crossref's own container-title contradicts its own date field for that specific DOI.

### Full pipeline order (now required — write this into the run sequence)
```
python scripts/generate_macros.py            # Table 1, per-lang, Williams tests, meta
python scripts/recompute_dir_morph_table.py  # DirMorph/EtaSq/DirMetric macros (Tier-1 only)
python scripts/generate_yearstrat_macros.py  # year-stratified + de-en held-out (appends, must run last)
python scripts/assert_paper_invariants.py    # 53 checks, must pass before compiling
python scripts/check_bibliography.py         # bib audit, run whenever citations change
```
Recompiled cleanly (pdflatex exit 0, only benign hyperref/float warnings) after all fixes. Cold-read abstract, §4.4/4.5, §5.3, §6 — all consistent with corrected macros, no stale hardcoded values remain (`grep` for old "0.21"/"+0.073"/"+0.28" DiD/gap values returns nothing).

## 2026-07-09 (Session 27 — Lookup table expansion: LOO + bootstrap + 15 languages)

### Summary
Expanded the direction-separated analysis from 6 to 15 languages (added kk/Kazakh, ta/Tamil, ha/Hausa, pl/Polish, is/Icelandic, gu/Gujarati, km/Khmer, lv/Latvian, ps/Pashto — all scores pre-existing). Added leave-one-out cross-validation (LOO overall 20/26 = 77%) and bootstrap winner-fraction CIs per cell. Key new finding: **X→en direction consistently favors CK23** (agglutinative 6/7, fusional 6/7 incl. de-en held-out), while **en→X agglutinative favors MetricX** (5/7, often by tiny margins; CK23>COMET in all 7 with bootstrap CI [1.00,1.00]). Also discovered `\DeEnCK23Rho` was an invalid macro name (digit in name → TeX tokenizer breaks it); renamed to `\DeEnKiwiRho`.

### Key results (direction_separated_winners.csv)
- Agglutinative X→en: CK23 wins 6/7 (LOO 6/7), bootstrap CI [0.57,1.00]
- Agglutinative en→X: MetricX wins 5/7 (LOO 5/7), CK23>COMET in all 7, CI [1.00,1.00]
- Fusional X→en: CK23 wins 5/6 direction-separated + de-en held-out = 6/7 (LOO 5/6)
- Fusional en→X: CK23 wins 4/6, CK23>COMET in all 6, CI [1.00,1.00]
- LOO overall: 20/26 = 77%; 86% for X→en cells specifically

### Updated macros
- All DirMorph*, EtaSq*, DirMetric* macros updated (η²_interact: 0.888→0.872)
- \DeEnCK23Rho renamed to \DeEnKiwiRho throughout

### Paper changes
- Lookup table (tab:lookup): split agglutinative→X→en + en→X rows, added LOO column, updated n/winner counts (now 27 pairs)
- §5.3 paragraph rewritten to reflect X→en/en→X split finding
- tab:dir_sep expanded: 6 languages → 15 languages, all direction-separated rows shown
- tab:dir_morph caption updated (n=7 agglutinative X→en, n=10 en→X)
- Hardcoded gaps updated: fusional X→en COMET-BLEU gap 0.16→0.11, agglutinative en→X 0.29→0.32
- Paper: 13 pages, Conclusion on page 8 (unchanged)

## 2026-07-08 (Session 26 — de-en held-out validation + overfull hbox fixes)

### Summary
Scored de-en (German→English, n=134,792) — the genuinely unseen X→en fusional pair absent from the WMT MQM German tier. CK23 wins: ρ=0.414 vs COMET ρ=0.383 and MetricX ρ=0.389. This confirms the lookup table prediction for the Fusional X→en cell. Fixed the SLURM `dirname $0` bug (script runs from `/var/spool` on compute nodes; switched to `SLURM_SUBMIT_DIR`). Fixed NaN tokenizer crash in CometKiwi23 by casting all inputs to `str()` and adding incremental CSV saves after each model. Fixed two persistent LaTeX overfull hboxes by reducing `\tabcolsep` (tab:lookup: 4pt→3pt, saves 10pt; tab:yearstrat: 3pt→2pt, saves 12pt).

### de-en results
- n=134,792 clean rows (4 null source/hyp dropped)
- CK23 ρ=0.414 (winner)
- COMET ρ=0.383
- MetricX ρ=0.389
- Lookup table prediction (X→en fusional → CK23): CONFIRMED

### Paper updates
- Added `\DeEnCK23Rho`, `\DeEnCOMETRho`, `\DeEnMetricXRho` macros to macros.tex
- Lookup table Fusional X→en row: 6→7 pairs, CK23 (4/6)→CK23 (5/7), added `$^\ddagger$` footnote
- §5.3 text: added sentence describing de-en as second held-out validation (fusional X→en cell)
- LaTeX: `\tabcolsep` reduced for tab:lookup (4→3pt) and tab:yearstrat (3→2pt) to fix overflows

### Pending
- Recompile paper on machine with pdflatex to confirm overflows resolved
- Potentially add de-en row to appendix tab:dir_sep

## 2026-07-07 (Session 25 — Direction mislabeling bug fix + held-out validation)

### Summary
Discovered and fixed a critical direction mislabeling bug: fi, tr, et, lt, cs, ja were all labeled `en_to_x` in direction_analysis.csv, but their data contains both X→en and en→X rows (confirmed from segment_id prefixes). Direction-separated the data using WMT DA quality scores joined positionally, recomputed the direction×morphology table, and updated all macros and paper text. The correction also provides a genuine held-out validation: 4/4 CK23 wins for X→en agglutinative (fi-en, tr-en, et-en, ja-en).

### 1. Bug discovery
From scores_comet.csv segment_id breakdown:
- fi: 46,145 fi-en (X→en) + 34,335 en-fi (en→X) — but labeled en_to_x
- tr: 30,186 tr-en (85%) + 5,171 en-tr (15%) — labeled en_to_x
- et: 20,496 et-en (61%) + 13,376 en-et (39%) — labeled en_to_x
- lt: 10,315 lt-en (54%) + 8,959 en-lt (46%) — labeled en_to_x
- cs: 51,097 cs-en + 70,943 en-cs + 13,804 de-cs — all labeled en_to_x
- ja: 46,747 ja-en (66%) + 24,434 en-ja (34%) — labeled en_to_x

### 2. Fix methodology
`scripts/analyze_direction_separated.py`:
1. Loaded WMT DA for 6 mixed-direction languages
2. Parsed direction from segment_id prefix (fi-en → x_to_en, en-fi → en_to_x)
3. Joined quality_score to metric scores by (segment_id, within-group row index)
4. Computed per-(lang, direction) Spearman ρ for all metrics

`scripts/recompute_dir_morph_table.py`:
- Merged direction-separated data with single-direction languages from correlations.csv
- Recomputed cell means, CIs, η² for the 2×3 table

### 3. Corrected direction×morphology table (COMET ρ)

| Cell | Old (pooled/mislabeled) | New (corrected) |
|------|------------------------|-----------------|
| X→en agglutinative | .613 (kk only, n=1) | .475 (kk+fi+tr+et+ja, n=5) |
| en→X agglutinative | .350 (contaminated) | .429 (clean) |
| X→en fusional | .288 | .305 |
| en→X fusional | .451 | .456 |
| pivot fusional | .354 | .410 |
| η²_interact | 0.911 | 0.888 |

### 4. Held-out validation (key result)
Direction-separated X→en agglutinative (fi-en, tr-en, et-en, ja-en): CK23 wins ALL FOUR. This is a genuine held-out validation — these pairs were previously pooled into the en→X cell and not used in the original lookup table construction.

| Pair | COMET | CK23 | Winner |
|------|-------|------|--------|
| fi-en | .525 | .578 | CK23 ✓ |
| tr-en | .527 | .588 | CK23 ✓ |
| et-en | .565 | .619 | CK23 ✓ |
| ja-en | .144 | .156 | CK23 ✓ |

Lookup table validation: 8/10 direction-separated agglutinative cells → CK23 wins. Exceptions: en-tr (MetricX 0.787 vs CK23 0.784, margin <0.004) and en-ja (MetricX 0.636 vs CK23 0.611).

### 5. Narrative change
Old claim: "en→X agglutinative shows the largest drop vs X→en" — WRONG (was driven by mislabeling).
New finding: "Direction effect is strongest for FUSIONAL languages (en→X fusional 0.456 vs X→en fusional 0.305, Δ=0.151). Agglutinative languages show near-parity across directions (0.475 vs 0.429), and CK23 is robust across both cells."

### 6. Paper updates
- macros.tex: all DirMorph, EtaSq, DirMetric macros updated to corrected values
- main.tex §5.2 (direction×morphology paragraph): Rewrote to focus on fusional direction effect; added footnote about mislabeling correction
- Table tab:dir_morph: X→en agglutinative cell now shows CI (n=5); bold moved to X→en agglutinative (held-out validated cell)
- Table caption (tab:dir_morph): Updated to describe n=5 X→en agglutinative + validation note
- Table caption (tab:dir_metric): Updated: "CK23 leads X→en overall (0.460 vs MetricX 0.451)"
- Mondshine contrast (line 282): Updated to fusional direction effect (Δ=+0.15)
- Lookup table (tab:lookup): Agglutinative n=6→10 direction-separated, CK23 8/10; fusional cells updated
- Appendix: Added tab:dir_sep with full per-(lang,direction) breakdown for 6 mixed-direction languages
- Compile: 13 pages, no errors

### 7. Updated "sincere expansion" checklist
- [x] OOD mechanism: Hebrew vs. Pashto contrast (done Session 24)
- [x] OOD mechanism: xCOMET-XL partial recovery (done Session 24)
- [x] Simpson's Paradox formal recommendation (done Session 24)
- [x] Held-out lookup table validation: 4/4 X→en agglutinative (done this session)
- [ ] Czech Simpson's Paradox via WMT DA (DA multi-year analysis pending; HF load killed in background)
- [ ] Score genuinely unseen pairs (de-en, de-cs, de-fr) via SLURM GPU job

## 2026-07-07 (Session 24 — Mechanism validation: Pashto-Hebrew contrast, Simpson's Paradox table, COMET-23 job prep)

### Summary
Implemented three expansions that upgrade the paper from "pattern documentation" to "mechanism validation": (1) Hebrew vs. Pashto abjad contrast formally validates OOD mechanism, (2) year-stratified vs. pooled correlation table formalizes Simpson's Paradox finding, (3) COMET-23 scoring infrastructure written and ready to submit.

### 1. Abjad mechanism validation (existing data, no GPU needed)

**Key insight**: Pashto is also an abjad script (Perso-Arabic/Nastaliq) and already in the pipeline. If COMET failure were a script-type effect, Pashto should also show compression. It does not.

**Results** (`scripts/analyze_abjad_mechanism.py`):
- Hebrew (abjad, NOT in COMET-22 training): ref-free advantage = +0.144 Spearman, COMET mean=0.423, z=-2.6σ
- Pashto (abjad, IN COMET-22 training via WMT20): ref-free advantage = +0.037, COMET mean=0.734, z=-0.4σ
- VERDICT: OOD training data mechanism confirmed. Same script family; different training coverage; opposite outcomes.

**Paper update**: Added 5-sentence paragraph to §5.2 presenting the Hebrew-Pashto contrast as mechanism validation. Hardcoded values: Kiwi-22 ps=0.295.

### 2. Simpson's Paradox systematic audit

**Results** from tier_anomaly.csv (COMET, MQM languages):
| Lang | Yrs | Pooled ρ | Strat mean | Δ (suppression) |
|------|-----|----------|------------|-----------------|
| ru | 2021,2022 | 0.157 | 0.442 | +0.285 SEVERE |
| zh | 2020-2022 | 0.447 | 0.502 | +0.054 |
| de | 2020-2022 | 0.425 | 0.426 | +0.001 |

**Paper update**: Added `\paragraph{Methodological recommendation: always stratify by year.}` and Table~\ref{tab:yearstrat} to §5.3. Suppression is unpredictable from resource level alone — depends on between-year system-pool heterogeneity.

### 3. COMET-23 Hebrew scoring (pending GPU job)

**Purpose**: Does COMET-23 (trained on WMT23, which includes Hebrew) show reduced score compression? This would directly validate the OOD mechanism.

**Scripts written**:
- `scripts/compute_comet23_he.py` — loads Hebrew MQM spans, scores with `Unbabel/wmt23-comet-da`, prints compression stats
- `scripts/slurm/run_comet23_he.sh` — SLURM job script (2h, 64G, 1 GPU)

**Pre-requisite** (run on login node):
```
.venv/bin/python -c "from comet import download_model; download_model('Unbabel/wmt23-comet-da')"
```

**Then submit**:
```
sbatch scripts/slurm/run_comet23_he.sh
```

### 4. Paper state after session
- 12 pages, Conclusion on page 8 (unchanged), no LaTeX errors
- §5.2 now has mechanism validation paragraph (Hebrew vs. Pashto contrast)
- §5.3 now has year-stratified table and methodological recommendation paragraph
- COMET-23 job ready to submit; paper updates pending those results

### 5. xCOMET comparison (no new job needed — existing data)

`Unbabel/wmt23-comet-da` does not exist publicly. Ran xCOMET-XL (already scored, includes WMT23 Hebrew training) Hebrew score distribution:
- COMET-22: mean=0.423, z=-2.83σ, Cohen's d(IQR)=3.81
- xCOMET-XL: mean=0.516, z=-0.94σ, Cohen's d(IQR)=5.82

Partial recovery consistent with OOD mechanism. Added one sentence to §5.2.

### 6. What remains to make this a sincere expansion
- [x] Validate OOD mechanism via Pashto-Hebrew contrast (done with existing data)
- [x] Validate OOD mechanism via xCOMET-XL partial recovery (done with existing data)
- [x] Turn Simpson's Paradox into a formal methodological recommendation (done)
- [ ] Held-out lookup table validation (needs additional WMT DA languages not in current set)

## 2026-07-06 (Session 23 — Story audit cuts: GEMBA, Tier 2 §4.2 paragraph, §5.1 reframing)

### Summary
Executed four story-audit cuts to tighten the paper around the core "typology predicts which metric to trust" thesis. PDF still compiles clean at 12 pages with Conclusion on page 8.

### Cuts made (`latex/main.tex`)
1. **Contributions bullet 4** (Intro): Removed GEMBA sentence ("scores near chance, setting a floor for LLM-evaluator requirements"). Retitled bullet from "Neural metrics are necessary, not optional" → "Neural metrics dominate across typological cells and resource tiers" to match the actual story.
2. **§5.1 GEMBA paragraph** (Discussion): Removed the standalone paragraph on GEMBA near-chance performance. GEMBA row remains in Table 1 — the data is still there, just not narrated.
3. **§5.1 subsection title**: Changed "Neural Metrics: Why the Gap is Largest Where It Matters" → "The Neural Advantage Scales With Typological Complexity" to connect this section to the typological thesis rather than defending neural vs n-gram.
4. **§4.2 Tier 2 paragraph**: Removed "Tier~2 synthetic annotation: Metric correlations for the seven Tier~2 languages…" paragraph. The Tier 2 caveat is already fully covered in §3.1 (pipeline description), Limitations, and the Future Work sentence. Removing the §4.2 paragraph eliminates redundant hedging mid-results.

### Rationale
All four orphans were narrating findings that either (a) don't contribute to the typological-prediction story or (b) were already covered elsewhere. GEMBA near-chance is a side-finding from a too-small backbone; foregrounding it suggested we were arguing "neural > surface" when the actual claim is "among neural metrics, typology determines which to choose." The Tier 2 paragraph doubled the limitation caveat already in §3.1 and Limitations.

### Paper state after session
- 12 pages, Conclusion on page 8, no LaTeX errors
- Title: "Lies, Damned Lies, and N-Grams: Typology, Not Resource Level, Predicts Which MT Metric to Trust"
- All figures regenerated with correct font scaling (scale factor S = W_fig / 3.31)
- Appendix: direction table (A.1), Ridge coefficients (A.2), discrimination figure (A.3)

## 2026-07-06 (Session 22 — Score discrimination figure, surface similarity ruling out, mechanism updated in paper)

### Summary
Ran surface similarity analysis (chrF for he/de/zh vs. WMT23 references), disproved the surface-dissimilarity hypothesis, identified the true mechanism (COMET training data OOD), generated a discrimination collapse figure, and updated §4.2 + §5.3 of the paper. PDF compiles clean at 12 pages.

### 1. Surface similarity analysis (`scripts/analyze_surface_similarity.py`)
- Computes chrF(hypothesis, reference) for he/de/zh from WMT23 span TSVs.
- **Key negative result**: Hebrew perfect-translation chrF = 0.77 ≈ German chrF = 0.77. Surface-dissimilarity hypothesis is WRONG.
- This forced revision of §5.3 mechanism explanation.
- Output: `results/surface_similarity.csv` (31,097 rows).

### 2. Mechanism identified: COMET training data coverage collapse
- COMET-22 trained on WMT 2017–2022; Hebrew first appears in WMT23 → OOD three-way cross-attention.
- **COMET on Hebrew**: mean=0.423, std=0.048, 7.5σ below cross-language mean, Cohen's d=0.47 (poor discrimination).
- **Kiwi-22 on Hebrew**: mean≈0.778 (normal), Cohen's d=1.73 (strong discrimination).
- Split is exact: ALL reference-based metrics show Hebrew score depression; ALL reference-free metrics show normal scores.

### 3. Score discrimination figure (`presentation_score_discrimination.png`)
- `plot_score_discrimination()` added to `make_presentation_plots.py`.
- 1×2 violin plots: Hebrew COMET-22 vs. Kiwi-22, bucketed by MQM quality (poor/medium/perfect).
- Cohen's d annotated in each panel.
- Saved to `results/plots/` and `latex/figures/`.
- Note: DE span-level scores not available in scores_comet.csv (only WMT20-22 DA format); figure focuses on Hebrew alone, which is the primary finding.

### 4. Paper updates (main.tex)
- **§4.2 Hebrew paragraph**: Added score compression numbers (mean=0.423, 7.5σ, Cohen's d=0.47 vs 1.73), reference-based/reference-free split, forward ref to §5.3 figure.
- **§5.3 mechanism section**: Added "Ruling out surface dissimilarity" and "Training data coverage collapse" paragraphs. Added `\label{fig:discrimination}` figure. Replaced surface-dissimilarity hypothesis with correct OOD explanation.
- PDF compiles clean: 12 pages.

### Open items
- Consider whether paper needs restructuring to center typological predictability (§4.4) more prominently.
- Surface similarity figure (scatter + boxplot) available in `results/plots/presentation_surface_similarity.png` — could go in appendix showing the negative result.
- ACL submission deadline: check current target.

---

## 2026-07-05 (Session 21 — GEMBA he/es scored, Ridge regression updated, coefficients figure added)

### Summary
Completed the pipeline for he/es: GEMBA scored for both languages, analysis regenerated, macros updated, Ridge regression re-run at n=33, paper updated with corrected r values and a new Ridge coefficients figure in the appendix.

### 1. GEMBA scoring (job 12504977, ~25 min, cs-1-3 A100-80GB)
- Wrote `scripts/compute_span_gemba.py` — mirrors `compute_span_scores.py` structure; scores GEMBA for he-en and en-es only, skips langs already in `scores_gemba.csv`, uses JSONL cache for checkpointing.
- Wrote `scripts/slurm/run_span_gemba.sh` (cs partition, 1 GPU, 4h, 64G).
- Scored: he = 12,441 segments, es = 11,289 segments. Total rows in scores_gemba.csv: 730,748.

**GEMBA results (Spearman ρ):**
- he: pairwise_acc=0.210, spa=0.497, spearman_r=? (see tier_summary)
- es: pairwise_acc=0.213, spa=0.456, spearman_r=−0.200
- **Key finding**: GEMBA-8B achieves ρ=−0.200 on es — worse than chance (pairwise_acc=0.213). For high tier (de/zh/ru/he), ρ=0.014 (near-random). Confirms 8B model is too small; result is a floor.

### 2. Analysis regenerated (job 12505059)
- correlations.csv and tier_summary.csv updated with GEMBA he/es rows.
- TierGEMBAHighRho = .014 (unchanged — he contribution averaged in but near-zero like de/ru/zh).
- TierGEMBAMedRho = −0.200 (es only; not displayed in Table 1 — medium GEMBA shows `---`).

### 3. Ridge regression re-run (login node, CPU)
- Ran at n=33 languages (all in typological_features.csv that appear in direction_analysis.csv).
- Previously ran at n=24. he and es added to MORPHOLOGY_TYPES (fusional) and TRANSLATION_DIRECTIONS.
- **Updated r values**: CometKiwi23 r=0.556→**0.56** (unchanged); CometKiwi r=0.45→**0.61** (improved with more data).
- Updated in §4.4: "r=0.61 for CometKiwi" (was 0.45).

### 4. Ridge coefficients figure (appendix A.2)
- Added `plot_ridge_coefficients()` to `make_presentation_plots.py`.
- 2×2 horizontal bar chart: top-6 standardized coefficients for comet, metricx, cometkiwi, cometkiwi23.
- Strongest predictors confirmed: num_cases and agglutinative for both Kiwi variants; logographic for MetricX.
- Figure placed in appendix (A.2) to preserve 8-page content limit. §4.4 now references it.

### 5. Macros (248 entries, 279 lines)
- All macros updated with new analysis. TierGEMBAHighRho=.014, TierGEMBAMedRho=−0.200 (not displayed).

### Open items
- Compile LaTeX to verify layout with appendix figure (need texlive on compute node or local).
- Paper ready for author review before ACL main track submission.
- Consider whether GEMBA es ρ=−0.200 (anticorrelated) warrants a footnote in Limitations.

---

## 2026-06-30 (Session 20 — he reference metrics fixed, es scored, LaTeX compiled)

### Summary
Fixed sacreBLEU reference lookup (was hitting OpenSSL / missing XML), scored all metrics for es (WMT24 en-es), fixed stale all-zero he BLEU/ChrF/BERTScore rows, regenerated correlations and macros, compiled PDF clean (9 pages).

### 1. Reference lookup fix (`build_sacrebleu_ref_lookup`)
- **Root cause**: `get_reference_files()` tried to decompress XML files that weren't present on compute nodes (`[digital envelope routines] unsupported` OpenSSL error).
- **Fix**: `build_sacrebleu_ref_lookup` in `wmt_mqm.py` now reads pre-cached `.ref-refA` / `.ref-refB` files directly from `~/.sacrebleu/<testset>/` instead. Falls back to the sacreBLEU API only if the cached files aren't found.
- Verified: he-en/wmt23 → 1,910 entries (ids 0–1909, offset=0); en-es/wmt24 → 997 entries (ids 2–998, offset=2).

### 2. compute_span_scores.py (new script)
- Generalizes compute_he_scores.py to handle both he and es.
- Logic: for each metric × lang, if rows absent → append; if present but reference-based and all-zero → delete stale rows and recompute; otherwise skip.
- Reference-based = {bleu, chrf, bleurt, bertscore}. COMET/xCOMET/Kiwi/MetricX skip he since already correct.

### 3. Span metrics job (12452512, cs-1-3, ~21 min)
- Removed 12,441 stale all-zero he rows from BLEU, ChrF, BERTScore (BLEURT was already correct).
- Recomputed he BLEU/ChrF/BERTScore with real WMT23 references.
- Scored all 9 metrics for es from scratch (~11,289 rows each).
- Every score CSV now has 730,748 total rows.

### 4. Analysis job (12455555)
Regenerated `results/correlations.csv` with corrected he and new es correlations. Key numbers:

**Hebrew (he)** — 12,441 segments, high-resource, human_mqm (Spearman ρ):
- BLEU: 0.422, ChrF: 0.373, BERTScore: 0.552, BLEURT: 0.056
- COMET: 0.191, xCOMET: 0.538, Kiwi-22: 0.569, Kiwi-23: 0.540, MetricX: 0.385
- Ensemble: 0.592
- Note: pairwise_acc/SPA numbers are much higher (0.59–0.78) — don't confuse with ρ

**Spanish (es)** — 11,289 segments, medium-resource, human_mqm (Spearman ρ):
- BLEU: 0.336, ChrF: 0.284, BERTScore: 0.450, BLEURT: 0.530
- COMET: 0.586, xCOMET: 0.556, Kiwi-22: 0.431, Kiwi-23: 0.444, MetricX: 0.625
- Ensemble: 0.589

### 5. generate_macros.py duplicate key fix
- Adding es (medium, human_mqm) created a second medium row per metric in tier_summary.csv, colliding with the existing medium (human_da) row.
- Fix: group tier_df by (metric, resource_tier) and mean-average across annotation tiers before keying macros. Tier = resource level, annotation method averaged out.
- Result: 213 entries → results/paper_stats.json + latex/macros.tex (244 lines).

### 6. LaTeX compile
- `module load texlive/2024 && pdflatex main.tex` → 9 pages, 0 errors, two passes.

### 6. Paper edits (same session)
- Fixed Table 1 caption: removed stale "he and es absent" language; updated to reflect they're now included in tier averages (he in High, es in Med averaged with human_da).
- Added he paragraph to Per-Language section: highlights COMET=0.191 vs Kiwi-22=0.569 gap; non-concatenative morphology hypothesis.
- Added es paragraph: notes strong MetricX=0.625, COMET=0.586 as upper bound for well-matched conditions.
- Added he and es to appendix Table A1 (he in X→en, es in en→X, sorted by COMET desc).
- Updated Limitations: removed outdated "he/es absent from High-tier" note; added caveat about he single-reference coverage.
- Fixed 24→26 languages with human annotations throughout.
- Compiled clean: 10 pages total (7 content + 2 references + 1 appendix), within ACL 8-page content limit.

### Session 20 continued — figures, abstract, ethics (2026-07-03)

**Figures regenerated** (previously from June 7, pre-he/es data):
- `presentation_language_heatmap.png` — now includes he (COMET=0.191 outlier) and es
- `presentation_tier_bar.png` — tier means updated with he/es averaging in
- Added new `presentation_kiwi23_vs_comet.png` — single-panel scatter, HE is the only outlier above the diagonal, used in §5.3

**New §5.3 figure**: replaced Table 5 with Figure 3 (scatter). More visually compelling; shows all 26 languages, making HE's isolation obvious.

**Abstract**: added sentence about script-type/QE finding (he COMET=0.191 vs Kiwi-23=0.540, Δ=+0.35).

**Contributions**: added 5th bullet about script type determining metric family.

**Ethics statement**: added before bibliography (datasets all public, no new human annotation, caveat about low-resource language use).

**Final compile**: 11 pages (8 content + 2 references + 1 appendix). Scatter figure lands on page 8; bibliography starts page 9. Exactly at limit.

### Open items
- Confirm submission venue and deadline (ACL 2026 is past; likely EMNLP 2026)
- Tier 2 near-zero correlations for lo/my still unexplained — possible genuine metric failure
- Consider multi-reference evaluation for he to confirm the abjad-coverage hypothesis

## 2026-06-29 (Session 19 — analysis OOM fixed, he and Tier 2 results confirmed)

### Summary
Fixed two pipeline bugs that prevented analysis from completing, then confirmed he-en and Tier 2 results.

### 1. Analysis job OOM — root cause: merge explosion on non-unique segment_ids
- **Root cause**: `segment_id` in score CSVs is NOT unique per row (e.g., `en-de_2020_news` is the domain key for all 549k DA rows, shared across ~67 rows). The analysis-only code did `pd.merge(full_scores_df, ckpt, on="segment_id")` which produced a Cartesian explosion: ~10k unique IDs × 68 rows × 68 rows = ~49M merged rows per metric call, OOM-killing even at 512G.
- **Fix**: Added uniqueness check before merging. If `ckpt["segment_id"].nunique() != len(ckpt)`, falls back to positional alignment (when row counts match) or partial fill with NaN for new rows. Added to `pipeline.py` analysis-only loader.

### 2. Row ordering bug — span fallback inserted mid-DataFrame
- **Root cause**: The span fallback block (he + es) was appended between Tier 1a (WMT MQM HF) and Tier 1b (WMT DA), so the new `full_scores_df` order was `[MQM_HF, he+es, DA, Tier2]`. But checkpoint CSVs were written in order `[MQM_HF, DA, Tier2, he]`. Positional alignment was completely scrambled — DA metric scores were assigned to he/es rows.
- **Fix**: Moved span fallback block to **after Tier2** in `pipeline.py`. New order: `[MQM_HF, DA, Tier2, span_fallback(he+es)]`. This matches checkpoint ordering for the first 707k rows (correct positional alignment) and puts new rows at the end where partial fill applies cleanly.

### 3. Confirmed results (job 12448719, cs-1-3, 512G)
**Hebrew (he)** — 12,441 segments, resource_tier=high, annotation_tier=human_mqm:
- xCOMET: 0.538, COMET-Kiwi 2022: 0.569, COMET-Kiwi 2023: 0.540, MetricX: 0.385, COMET: 0.191
- Ensemble: 0.592
- BLEU/BERTScore/ChrF: NaN (those score CSVs predate compute_he_scores.py — needs re-run for those 3)

**Tier 2 (synthetic_mqm)** — 0 NaN correlations (was all-NaN before the return_full_text fix):
- ht: 0.159 (best), sw: 0.100, th: 0.093, am: 0.053, ka: 0.056, my: -0.003, lo: -0.040
- Near-zero for lo/my/th is a finding (metrics effectively random-level for these languages)

### Open items
- Run BLEU/ChrF/BERTScore for he rows (compute_he_scores.py already handles this — just resubmit run_he_metrics.sh which skips already-present segment_ids)
- Run metrics for es (en-es WMT24 MQM) — currently all-NaN; needs a compute_es_scores.py or extending compute_he_scores.py
- Regenerate paper macros via generate_macros.py now that correlations.csv is updated
- Tier 2 near-zero correlations: worth investigating whether this is a quality issue with synthetic annotations or a real metric failure on those languages

---

## 2026-06-27 (Session 18 — he-en fix, Tier 2 bug fix, LaTeX cleanup, venue: ACL main track)

### Summary
Three open issues from Session 17 addressed before data re-runs. Also fixed duplicate entries in research log (cleanup from Session 17 reordering).

### 1. LaTeX overfull hbox fixed
The `tab:dir_metric` table (direction × 5 metrics) was 15.23pt over column width. Fixed by reducing `\tabcolsep` from 4pt to 2pt for that table. Recompile: clean, 9 pages, zero overfull boxes.

### 2. he-en root cause identified and fix implemented
- **Root cause**: `RicardoRei/wmt-mqm-human-evaluation` HF dataset does not include `he-en` (WMT23). The pipeline only loaded from HF, so Hebrew was silently missing from all results.
- **Data status**: `mqm_generalMT2023_heen.tsv` (4.7 MB, 12,484 span rows) exists in `../wmt-mqm-human-evaluation/generalMT2023/heen/`.
- **Fix applied**:
  - `load_wmt_mqm_spans`: Fixed `segment_id` to include system name (`he_<system>_<globalSegId>`), so each (system × segment) pair is unique. Previously fell through to row-index fallback since neither `globalsegid` nor `docsegid` matched the old `seg_id` check.
  - `pipeline.py`: After HF load, detects which `wmt_mqm_pairs` languages are absent, then falls back to span TSV for those. Loads he-en via `load_wmt_mqm_spans` → `annotations_to_sentence_scores` and tags as `HUMAN_MQM`.
  - `scripts/compute_he_scores.py`: Standalone script to compute all metrics for he rows only and append to existing `scores_{metric}.csv` checkpoints. Lets `--analysis-only` pick up he via segment_id merge without re-running the full pipeline.
  - `scripts/slurm/run_he_metrics.sh`: SLURM job (dwmatrix, 256G, 6h, 1 GPU) to submit.
- **Verified**: Span loading produces 12,441 sentence scores, quality_score std=0.36 (plenty of signal).
- **Status**: Code ready. Need to submit `run_he_metrics.sh`, then `run_analysis_only.sh`.

### 3. Tier 2 synthetic MQM — root cause identified and fix implemented
- **Root cause**: HF text-generation pipeline returns `generated_text` including the full prompt by default (`return_full_text=True`). The prompt template contains "NO ERRORS" (in the examples section). So `"NO ERRORS" in text.upper()` was always True, and every single segment was classified as `no_error`. This produced zero variance in quality_score → NaN Spearman for all 7 Tier 2 languages.
- **Fixes applied**:
  - `synthetic_mqm.py`: Added `return_full_text=False` to pipeline call (primary fix).
  - Prompt: Added full language names (`_LANG_NAMES` dict), added multilingual examples (Swahili, Amharic), strengthened the "find errors" instruction.
  - Sampling: Changed `do_sample=False` → `do_sample=True, temperature=0.3` to prevent mode collapse.
  - Old caches: Need manual deletion (`rm data/cache/synthetic_mqm_*.jsonl`) — 7 files, all-`no_error` data.
  - `scripts/slurm/run_tier2_regen.sh`: SLURM job (dw, 64G, 12h, 1 GPU) to regenerate.
- **Status**: Code ready. Need to: (1) delete bad caches, (2) submit `run_tier2_regen.sh`, then (3) submit `run_analysis_only.sh`.

### Submit order
```
# 1. Delete bad Tier 2 caches
rm data/cache/synthetic_mqm_*.jsonl

# 2. Submit he-en metrics job
sbatch scripts/slurm/run_he_metrics.sh

# 3. Submit Tier 2 regeneration
sbatch scripts/slurm/run_tier2_regen.sh

# 4. After both finish, re-run analysis
sbatch scripts/slurm/run_analysis_only.sh
```

### Venue target: ACL main track (no specific deadline set yet)

### Files added/modified this session
- `latex/main.tex` — tabcolsep fix
- `src/mqmbench/data/wmt_mqm.py` — segment_id now includes system name
- `src/mqmbench/pipeline.py` — span fallback for HF-missing pairs; added `load_wmt_mqm_spans` import
- `src/mqmbench/data/synthetic_mqm.py` — `return_full_text=False`, improved prompt, temperature=0.3
- `scripts/compute_he_scores.py` — new standalone he metric scorer
- `scripts/slurm/run_he_metrics.sh` — new SLURM job
- `scripts/slurm/run_tier2_regen.sh` — new SLURM job
- `scripts/slurm/run_analysis_only.sh` — new SLURM job
- `notes/research_log.md` — duplicate cleanup + this entry

---

## 2026-06-26 (Session 17 — constructive element: typological lookup table + predictor)

### Motivation
The paper diagnosed metric unreliability across typologically diverse languages but had no constructive element — no solution for practitioners. Goal this session: add one. Decision: a **validated lookup table** giving practitioners a concrete recommendation ("for your language profile, use this metric instead of BLEU"), supported by a Ridge regression predictor that validates the patterns are typologically driven rather than noise.

### New research direction: metric reliability predictor
Framing: "evaluation metrics are unreliable for typologically diverse languages in predictable ways — given a language's typological profile, predict which metrics to trust."

Target variable: `spearman_r(metric) − spearman_r(BLEU)` per language — the advantage a metric has over BLEU. Predicting absolute Spearman r just learns "MetricX is generally best"; BLEU-relative advantage captures when typology changes that ranking.

### Typological features gathered
Downloaded WALS (World Atlas of Language Structures) CLDF data from GitHub. Selected features with best coverage for our 31 languages:
- **81A** (word order: SOV/SVO/etc.) — 28/31 from WALS, 3 manual
- **49A** (number of morphological cases) — 20/31 from WALS, 11 manual
- **26A** (prefixing vs. suffixing) — 26/31 from WALS, 5 manual
- **word_segmentation** — derived: 0 for Thai/Lao/Khmer/Burmese/Japanese/Chinese (no orthographic word spaces), 1 otherwise

Also tried Grambank but it was missing German, Bengali, Gujarati, Kazakh — WALS had better coverage for major world languages.

Manual values (ht, kk, ps, and individual missing features) sourced from standard typological references, flagged in `manual_fields` column.

Output: `data/typological_features.csv` (31 rows, fully complete)
Script: `scripts/build_typological_features.py`

### Predictor design and results
**Architecture:** One Ridge regression per metric (8 models: bertscore, bleurt, chrf, comet, cometkiwi, cometkiwi23, metricx, xcomet). Each model predicts BLEU-relative advantage from typological features only — no metric identity feature, since each model IS the interaction. 24 data points × ~8 features per model.

**Evaluation:** Leave-one-language-out CV (LOLO-CV). Best results:
- cometkiwi: LOLO-CV Pearson r=0.561
- cometkiwi23: r=0.449
- bertscore: r=0.402
- others: r=0.1–0.3

**Recommendation accuracy** (top-1 metric matches actual best): 3/24 — too low to claim a deployable tool.

**Key coefficient patterns:**
- `num_cases` → positive for cometkiwi and cometkiwi23: reference-free metrics gain most where morphological complexity defeats n-gram overlap
- `agglutinative` → positive for reference-free metrics
- `logographic` → positive for MetricX
- `direction=pivot` → negative for reference-free metrics (pivot pairs stress all metrics)

### Main constructive contribution: validated lookup table
Rather than overclaiming a predictor, the paper's constructive element is a **validated lookup table** organized by typological profile. For the 24 languages with human annotations, we know the actual best metric — the table gives that directly, organized so practitioners can find the closest profile match for an unseen language.

**Patterns (all observed from data, not predicted):**

| Profile | Best metric | Consensus |
|---|---|---|
| Agglutinative, any direction | CometKiwi23 | 6/6 unanimous |
| Isolating + x→en, no word spaces | MetricX | 2/2 unanimous |
| Fusional + pivot | MetricX | 4/5 |
| Fusional + x→en | CometKiwi23 | 2/3 |
| Fusional + en→x | CometKiwi23 | 3/8 (noisy) |

Gain over BLEU ranges from +0.14 to +0.48 Spearman ρ across all profiles — the "use a neural metric" message is strong even where the choice between specific neural metrics is uncertain.

Output: `results/predictor/lookup_table.csv`

**Paper framing:** Table = practitioner contribution. Predictor (LOLO-CV r=0.6 for cometkiwi) = validation that patterns are typologically driven. Honest limitation: fusional + en→x cell has 8 languages with no clear winner; disclosed explicitly.

### Files added this session
- `data/grambank/` — WALS CLDF CSVs (languages, values, parameters, codes)
- `data/typological_features.csv` — 31-language typological feature table
- `scripts/build_typological_features.py` — pulls from WALS, fills manual gaps
- `scripts/build_metric_reliability_predictor.py` — per-metric Ridge regression
- `results/predictor/` — cv_predictions.csv, coefficients.csv, lookup_table.csv, recommendation_table.csv, summary.json
- `latex/main.tex` — new `\subsection{Typological Predictors of Metric Choice}` with Table 4 (lookup table) and predictor validation paragraph

### Compile status
Clean compile: 9 pages, no errors. One pre-existing overfull hbox in the direction×morphology table (line 251, 15pt, not introduced this session). pdflatex at `/apps/texlive/2024/bin/x86_64-linux/pdflatex`.

## 2026-06-11 (Session 16 — SSOT macros pipeline)

### What we did

Implemented a single-source-of-truth (SSOT) pipeline where every numeric claim in the paper is sourced from experiment CSVs via code, stored in a JSON file, and rendered in LaTeX via auto-generated macros.

**`scripts/generate_macros.py`** — new script that:
- Reads `results/correlations.csv`, `direction_analysis.csv`, `direction_morphology_interaction.csv`, `tier_summary.csv`, `williams_tests.csv`
- Recomputes direction×morphology cell means from per-language data using the **correct** MORPHOLOGY dict (bypassing the stale `direction_morphology_interaction.csv` for x_to_en cells affected by the km reclassification)
- Outputs `results/paper_stats.json` (191 entries, each with value, fmt, source, note)
- Outputs `latex/macros.tex` (auto-generated `\newcommand` definitions)
- Flags 9 manual entries that are not yet sourced from a CSV (year-stratified Russian/German values, total segment count, n_metrics)

**`results/paper_stats.json`** — SSOT for all paper statistics. Every value has a `source` field pointing to the CSV (or `manual/*` for values requiring year-split re-analysis).

**`latex/macros.tex`** — 191 `\newcommand` definitions, regenerated by running `python3 scripts/generate_macros.py`.

**`latex/main.tex`** — updated with `\input{macros}` and 164 hardcoded numbers replaced by macros throughout: abstract, intro, Table 1, per-language section, Table 2, Table 3, Discussion, Conclusion, appendix table.

### Bugs found and fixed in the paper

Three factual errors discovered by tracing each number to its source:

1. **"32 languages" → 31**: `correlations.csv` has 31 unique languages. The 32nd was likely `es` or `he` (both absent from all data tiers). Fixed via `\NumLanguages` macro everywhere.

2. **"Zulu n=3,200" → 2,968**: `direction_analysis.csv` has n=2,968 for `zu`. Fixed via `\LangNZU` macro.

3. **Williams t attribution wrong**: Paper said "+21,550 (xCOMET vs. BLEU, de)" — the value +21,550 is real but belongs to zh xCOMET vs. COMET (not de, not vs. BLEU). Similarly, "-38,335" was attributed to de but is cs BERTScore vs. COMET. The actual extreme non-ensemble t-values are +26,098 (MetricX vs. COMET, zh) and -51,348 (BLEU vs. COMET, cs). Paper text corrected; macros `\WilliamsMaxT` and `\WilliamsMinT` now pull correct values automatically.

### Manual entries (to automate in future)

Nine entries still sourced manually (`source: "manual/*"`):
- `TotalSegments` (707,347) — from pipeline stdout, not a CSV
- `NumMetrics` (10) — static
- Russian year-stratified: `RuWmtOneRho` (0.383), `RuWmtTwoRho` (0.501), `RuWmtOneN` (15,600), `RuWmtTwoN` (19,725)
- German year-stratified: `DeWmtTwoZeroRho` (0.497), `DeWmtTwoOneRho` (0.323), `DeWmtTwoTwoRho` (0.456)

To eliminate all manual entries: add a `year_stratified_correlations.csv` output to the pipeline (already computable from the existing data — just needs a `groupby(['lang','wmt_year'])` pass).

### Workflow going forward

Run `python3 scripts/generate_macros.py` after any re-analysis to regenerate `macros.tex`. Paper numbers update automatically on next LaTeX compile. No manual number-copying needed.

## 2026-06-07 (Sessions 13–15 — full paper revision from class report to conference-ready draft)

### What changed across sessions 13–15

#### Content additions (session 13)
- Williams p-values: fixed `p≈0` → explicit statement about floating-point underflow; t-statistic range reported (+21,550 to −38,335); Zulu xCOMET exception (p=7.2×10⁻⁸) noted
- Direction-stratified Table 3: BLEU/ChrF/COMET/xCOMET/MetricX by direction (en→X, X→en, pivot)
- Russian Simpson's Paradox paragraph: WMT21-only ρ=0.383, WMT22-only ρ=0.501, aggregate ρ=0.157; German comparison included
- Khmer paragraph: COMET ρ=0.476, MetricX ρ=0.516; isolating Austroasiatic, single-year Wikipedia domain
- Domain decomposition paragraph: exact numbers from domain_controlled_comparison.csv; Kocmi 2024 direct quote
- Limitations updated: removed stale "pending analysis" text; he/es missing explained, Simpson's Paradox warning for ru/de

#### Major paper revision (session 14)
- **Title**: "Lies, Damned Lies, and N-Grams: Translation Direction and Morphology Demand Neural Evaluators" (backup: "BLEU in the Face" commented in source)
- **Abstract**: full rewrite — leads with Ukrainian finding, Simpson's Paradox, η²=0.72, GEMBA floor
- **Morphological classification fixes (critical)**:
  - km (Khmer): was agglutinative → corrected to **isolating** (Austroasiatic/Mon-Khmer)
  - my (Burmese): was agglutinative → corrected to **isolating** (Sino-Tibetan/analytic)
  - These change Table 2: x_to_en+agglutinative 0.545→0.613 (kk only), x_to_en+isolating 0.447→0.462 (zh+km)
  - Updated in `correlation.py` MORPHOLOGY_TYPES and `plots.py` title comment
- **lv/lt morphology clarified**: Latvian and Lithuanian are fusional Baltic (IE), not agglutinative; top-performers paragraph rewritten to attribute cluster to data quality not morphology
- **Figures regenerated**: both presentation PNGs now show all 10 metrics (were showing 4)
- **Citations added**: Llama 3 (dubey2024llama3), Williams 1959 (williams1959), Bojar 2017 (bojar2017wmt), Freitag 2021 (freitag2021experts)
- **Related Work section added** (5 paragraphs): WMT Metrics Shared Task, MQM annotation quality, domain/resource shift, morphology in MT, typological diversity
- **Discussion expanded**: two new subsections — "Neural Metrics: Why the Gap is Largest Where It Matters" and "Domain Is the Confounding Variable, Not Resource Level"
- **Appendix added**: per-language COMET+MetricX table grouped by direction with corrected morphology labels
- **Table 2 caption**: explains --- cells, notes km/kk cell membership
- **Table 3**: MetricX bolded as best metric per direction row
- **figures/ directory**: `latex/figures/` created; both PNGs copied in; paper references `figures/` instead of `../results/plots/`
- **`--analysis-only` robustness fix**: changed from positional alignment (`ckpt[metric].values`) to segment_id-based merge; fallback to positional if no segment_id column

#### Structural restructuring (session 15)
- **Added §1 Introduction**: hook, gap statement, 4-item contributions list with key numbers, section roadmap
- **Added §6 Conclusion**: 4 paragraphs covering main findings, practical implications, future work
- **Moved Related Work**: from §4 (after Discussion) to §2 (after Introduction) — standard ACL position
- **Removed duplicate Limitations**: `\subsection{Limitations}` inside Discussion removed; only `\section*{Limitations}` remains (ACL standard)
- **Removed Research Questions subsection**: folded into Introduction
- **Added section labels**: `\label{sec:related/method/results/discussion/conclusion}` for intro roadmap cross-refs
- Final structure: Introduction → Related Work → Methodology → Results → Discussion → Conclusion → Limitations* → References → Appendix
- **Compile**: clean, 9 pages

### Current paper state
- 9 pages, standard ACL structure, clean compile
- All results from June 5 analysis run (10 metrics, 707k segments, 32 languages)
- he-en absent (not in RicardoRei HF dataset — only available via Google TSV release)
- Tier 2 results exploratory (synthetic annotations not human-validated)
- Target venue: WMT workshop or EMNLP Findings

### he-en loader investigation (session 13)
Determined that `RicardoRei/wmt-mqm-human-evaluation` only contains en-de, zh-en, en-ru at any cached version. he-en (WMT23) and en-es (WMT24) are only in Google's TSV release. Decision: not worth adding — he-en in x_to_en+fusional cell (already confounded by ru/uk), and keeping single-source HF pipeline is more reproducible. Documented in paper Limitations.

## 2026-06-07 (Session 15 — restructured to standard ACL format: Introduction + Conclusion added)

### Changes
- Added §1 Introduction: hook, gap statement, 4-item contributions list, roadmap
- Added §6 Conclusion: 4-paragraph summary of findings, practical recommendations, future work
- Moved Related Work from §4 (after Discussion) to §2 (after Introduction) — standard ACL position
- Added \label{sec:related}, \label{sec:method}, \label{sec:results}, \label{sec:discussion}, \label{sec:conclusion} for \S cross-refs in intro roadmap
- Removed duplicate \subsection{Limitations} inside Discussion (kept only \section*{Limitations})
- Removed \subsection{Research Questions} — folded into Introduction
- Paper now: 1 Introduction, 2 Related Work, 3 Methodology, 4 Results and Analysis, 5 Discussion, 6 Conclusion, Limitations*, References, Appendix
- Compile: clean, 9 pages

## 2026-06-07 (Session 14 — major paper revision: title, abstract, related work, 8 pages, morphology fixes)

### Changes
- **Title**: "Lies, Damned Lies, and N-Grams: Translation Direction and Morphology Demand Neural Evaluators" (backup: "BLEU in the Face" commented in source)
- **Abstract**: Full rewrite — leads with findings, mentions Ukrainian domain confound, Simpson's Paradox, η²=0.72 interaction, GEMBA floor
- **Morphology fix (critical)**: km (Khmer) was misclassified as agglutinative — corrected to isolating (Austroasiatic/Mon-Khmer). my (Burmese) also corrected to isolating. This changes Table 2: x_to_en+agglutinative 0.545→0.613 (kk only), x_to_en+isolating 0.447→0.462 (zh+km)
- **lv/lt morphology**: Latvian and Lithuanian are FUSIONAL (Baltic IE), not agglutinative. Paper text corrected; the "top performers" paragraph now correctly attributes the Baltic/Finnic/Turkic cluster to data quality, not morphology
- **Figures regenerated**: both presentation_tier_bar.png and presentation_language_heatmap.png now show all 10 metrics (was 4)
- **Citations added**: Llama 3 (dubey2024llama3), Williams 1959 (williams1959), Bojar 2017 WMT DA (bojar2017wmt), Freitag 2021 MQM experts (freitag2021experts)
- **Time log**: removed
- **Related Work section added**: WMT Metrics Shared Task, MQM/annotation quality, domain/resource shift, morphology in MT evaluation, typological diversity in NLP
- **Discussion expanded**: "Neural Metrics: Why the Gap is Largest Where It Matters" + "Domain Is the Confounding Variable, Not Resource Level" subsections; practical implications explicit
- **Appendix**: full per-language direction table (COMET + MetricX, grouped by direction, correct morphology labels)
- **Table 2 caption**: now explains --- cells, corrected morphology cell memberships noted explicitly
- **Table 3**: MetricX bolded as best metric in all three direction rows
- **Compile**: clean, 8 pages (target achieved)

## 2026-06-07 (Session 13 — all review items implemented, paper finalized)

### Changes to latex/main.tex
All items from `notes/claude_review.md` that were doable without external work:

1. **Williams t-statistics**: Fixed `p ≈ 0` → explicit statement that p-values underflow to 0.0 in double precision at large n; now reports t-statistic range (+21,550 to −38,335) and the one non-underflow case (Zulu xCOMET, p=7.2×10⁻⁸).

2. **Direction-stratified Table 3**: Added `tab:dir_metric` with BLEU/ChrF/COMET/xCOMET/MetricX by direction (en_to_x, x_to_en, pivot). Key numbers: en_to_x MetricX=0.524, pivot MetricX=0.530 (counterintuitively highest), x_to_en COMET=0.400.

3. **Domain decomposition paragraph**: Expanded Ukrainian discussion in `\subsection{Benefits}` to include exact domain-controlled numbers (x_to_en news/wiki langs ρ=0.33–0.61 vs Ukrainian other=0.001) and direct Kocmi 2024 quote about "collected separately, comprising news data and four other separate domains."

4. **Russian Simpson's Paradox**: Updated Russian anomaly paragraph with year-stratified breakdown (WMT21-only ρ=0.383, WMT22-only ρ=0.501, aggregate ρ=0.157). Added German comparison (2020: 0.497, 2021: 0.323, 2022: 0.456, aggregate: 0.425). Mechanistic explanation: heterogeneous MT system generations across years, not a Russian language property.

5. **Khmer paragraph**: Added analysis showing Khmer (COMET ρ=0.476, MetricX ρ=0.516) outperforms medium-resource languages like Japanese (0.279) and Hindi (0.194). Attributes this to single-year Wikipedia domain data with clean reference translations.

6. **Limitations updated**: Removed stale "pending the final analysis run" text; replaced with concrete limitations (he/es missing, Simpson's Paradox warning for ru/de aggregate, supplementary files for full direction×morphology results).

7. **Full recompile**: pdflatex + bibtex + pdflatex×2 cycle — clean compile, 7 pages, no errors.

### Remaining before submission
1. Investigate he-en loader failure (silently dropped) — should be in High tier
2. Tier 2 human validation (200 ESA segments) — external human annotation needed
3. Possible: camera-ready formatting pass if submitting to a venue

## 2026-06-05 (Session 12 — first full 10-metric results, analysis speed fix, paper draft pass)

### What ran
All 10 metric jobs completed (bleu, chrf, bertscore, bleurt, comet, xcomet, cometkiwi, cometkiwi23, metricx, gemba) across 707k segments. xCOMET needed a 7× speedup: patched Lightning Trainer with `precision="bf16-mixed"` (13.9GB model → ~7GB, memory-bandwidth bottleneck lifted). GEMBA rewrote from `hf_pipeline` to direct `model.generate()` with bfloat16 and left padding; completed in 1:22.

Analysis job timed out twice (2h then 6h limit) because `correlate_metric_vs_human` ran 1000 Spearman bootstraps for every (lang × metric) call in every sub-analysis. Fixed: pass `n_boot=0` to all sub-analyses (direction, domain, system-level, length); keep `n_boot=1000` only for main `correlations.csv`. Also vectorized `_bin` in `run_length_analysis` with `np.select`. Job 12114557 finished at ~45 min with the fix.

### Root cause found: checkpoint merge OOM
The original checkpoint used `segment_id` as merge key. `segment_id` is NOT unique — multiple rows share the same ID (e.g., `en-de_2020_news`). Merging created a Cartesian product → MemoryError caught by `except Exception: pass` → job wrote only its own metric, clobbering others. Fixed with per-metric files (`scores_{metric}.csv`) using positional alignment — no shared state, no locking, no races.

### First complete results (10 metrics)
**Tier summary — top performers:**
- High (MQM, de/ru/zh): xCOMET ρ=0.427, MetricX-24 ρ=0.402; ensemble ρ=0.415
- Medium (DA): MetricX-24 ρ=0.550, CometKiwi-23 ρ=0.504; ensemble ρ=0.526
- Low (DA, ha/km/ps): MetricX-24 ρ=0.383, CometKiwi-23 ρ=0.368; ensemble ρ=0.363
- GEMBA (Llama-3.1-8B) on MQM: ρ=0.035 — barely above chance, worse than BLEU

**Per-language highlights:**
- Latvian COMET ρ=0.746 (highest); followed by Lithuanian 0.634, Estonian 0.631, Finnish 0.627, Kazakh 0.613 — NOTE: lv/lt are FUSIONAL Baltic, not agglutinative; et/fi/kk are agglutinative; cluster explained by data quality not morphology
- Russian ρ=0.157 anomaly: all metrics weak despite n=35,325 and tight CIs [0.148, 0.168]. Likely multi-year WMT21+22 pooling heterogeneity (not domain confound)
- Ukrainian ρ=0.001 confirmed domain confound (uk-en_2022_other, conversational register)
- he and es absent from High tier — he-en not in HF dataset; en-es (WMT24) silently dropped

**Direction × Morphology (COMET):**
- interaction_eta_sq = 0.721 — dominant effect; direction alone = 0.104, morphology alone = 0.175
- x_to_en + fusional = 0.288 (dragged down by ru=0.157 and uk=0.001)
- en_to_x + agglutinative = 0.525 (Baltic/Finnic/Turkic cluster)

**Tier 2 (synthetic_mqm):** All NaN — zero variance in synthetic quality scores for all 7 languages. New GEMBA implementation did not fix this; the model still assigns uniform scores. Needs human validation (200 ESA segments per language minimum).

### Paper updates (latex/main.tex)
- Title reframed: "What Looks Like a Low-Resource Problem Is Often a Domain Problem"
- Abstract updated to 10 metrics, 32 languages, SPA
- Metrics section restructured with 5 paragraph groups
- Tier 2 section: 7 languages, circular evaluation caveat, explicit validation requirement
- Telegram claim removed; Ukrainian now attributed to `uk-en_2022_other` (domain "other") + Zouhar 2024
- Evaluation protocol: added SPA (WMT 2024 standard), Deutsch 2023 tie calibration
- Direction×morphology: full methodology section + results table with real eta_sq values
- Results tables fully filled with June 5 numbers
- Russian anomaly paragraph added
- Per-language highlights updated (Latvian 0.746, agglutinative cluster)
- 11 new bib entries added: BLEURT, xCOMET, MetricX-24, CometKiwi, Zouhar 2024, Kocmi 2024, Lu 2024, Mondshine 2025, Yari 2025, Bugliarello 2020, Thompson 2024 SPA, Deutsch 2023

### Remaining before submission
1. Investigate he-en loader failure (silently dropped) — should be in High tier
2. Tier 2 human validation (200 ESA segments) — external human annotation needed

## 2026-05-29 (Session 11 — cascade of fixes: checkpoint merge, GEMBA gating, MetricX-24, wall times)

### What failed and why

**Job 12026429-12026433 (parallel batch)**: All metrics timed out or OOM'd.
- Root cause 1: GEMBA was running in EVERY job (not just the gemba job) because the GEMBA
  check was `if getattr(cfg.metrics, 'run_gemba', False)` which ignored `only_metrics`.
  Fixed: `if run_gemba and (only_metrics is None or "gemba" in only_metrics)`.
- Root cause 2: Checkpoint saves overwrote each other. Each job saved `id_cols + added_columns`
  which only included the current job's metric, clobbering previous jobs' results.
  Fixed: merge-on-save with `fcntl.flock` file locking to prevent race conditions.
- Root cause 3: GEMBA max_new_tokens=256 → ~48h for 85k segments. Fixed to 64 (~12h).
- Root cause 4: Memory limit too low (32G-64G). Compute-node cgroup accounting adds ~60-100GB
  overhead vs 2.37GB measured on login node (likely CUDA context + shared library pages).
  All jobs now use 128G minimum.

### MetricX-24 added

`google/metricx-24-hybrid-large-v2p6-bfloat16` implemented from scratch (no package needed):
- MT5ForConditionalGeneration with decoder input=pad, reads logit at token 250089 (<extra_id_10>)
- Score range [0,25] raw; we return 25-raw so higher=better like COMET
- bfloat16 model ~1.2GB; tokenizer = google/mt5-large sentencepiece
- Both model and tokenizer pre-cached on login node
- Added to `metrics.run` list, integrated into pipeline, included in ensemble

### Analysis fixes

- `run_correlation_analysis`: added `group[metric].isna().all()` guard
- `run_williams_tests`: filter to complete cases before t-test (handles GEMBA NaN on DA tier)
- `analysis_only` mode: now computes ensemble metric from checkpoint data
- `run_direction_morphology_interaction` and `run_domain_controlled_comparison` added
- `TRANSLATION_DIRECTIONS`: fixed to include pivot category (fr/bn/hi/xh/zu)

### Current running jobs (as of 2026-05-29)

- 12057144  mqm_bleu_etc  128G 3h  — bleu/chrf/bertscore/comet
- 12056303  mqm_bleurt    128G 3h
- 12056304  mqm_xcomet    128G 20h
- 12056305  mqm_cometkiwi 128G 6h
- 12056306  mqm_metricx   128G 3h
- 12056814  mqm_gemba     128G 20h  — resumes from 10k cached segments
- 12057146  mqm_analysis  32G  1h   — afterok all 6

### Memory mystery (unresolved)

Compute-node jobs OOM at 32G-64G even though data loading measures 2.37GB on login node.
Memory probe job 12057185 submitted to diagnose exact breakdown. If CUDA context is the issue,
all jobs need ≥128G regardless of model size. Updated submit_chain.sh accordingly.

### submit_chain.sh updated

Now uses 128G for ALL metrics, includes metricx and bleu_etc, 20h for xcomet/kiwi23/gemba.
Run `bash scripts/slurm/submit_chain.sh` to resubmit cleanly from scratch if needed.

## 2026-05-27 (Session 10 — OOM root cause, dwmatrix, chain jobs, review triage, session end)

### Final job chain (dependency chain, one metric per process)

Previous approach (all metrics in one process) accumulated MaxRSS across sequentially loaded
models and hit 510 GB even with 512G limit. Root cause confirmed by diagnostic job 12014897:
xCOMET-XL alone costs 28.86 GB RSS (14 GB sacct), but MaxRSS never decreases after gc.collect()
so sequential model loading accumulates — 4 models × ~30 GB = OOM regardless of limit.

Fix: run each metric in its own SLURM job via dependency chain. Fresh Python process per metric,
MaxRSS resets. Added `--only-metrics` and `--analysis-only` flags to run_pipeline.py + pipeline.py.

Submitted chain on dwmatrix, all jobs queued:
- 12025725  mqm_xcomet     RUNNING  (128G, 6h) — started immediately
- 12025726  mqm_bleurt     PENDING  afterok:12025725
- 12025727  mqm_cometkiwi  PENDING  afterok:12025726
- 12025728  mqm_cometkiwi23 PENDING afterok:12025727
- 12025729  mqm_gemba      PENDING  afterok:12025728  (64G, 20h — Llama)
- 12025730  mqm_analysis   PENDING  afterok:12025729  (32G, 1h)

Expected completion: ~22h from submission (xcomet ~3h, bleurt ~1h, kiwi22 ~1.5h,
kiwi23 ~2h, GEMBA ~14h, analysis ~30min). Check with: squeue -u it238

### Tier 2 ESA validation decision

ESA (Expected Score with Annotation) is the WMT 2024 annotation protocol — combines a 0–100
numeric DA-style score with MQM-style error spans in one pass, cheaper than MQM but richer
than plain DA. The peer review flagged validating Tier 2 synthetic annotations against ≥200
ESA-rated segments as the single biggest rejection risk. Decision: no annotators available,
so Tier 2 validation will NOT be done before submission. Will present Tier 2 as exploratory
and frame results with appropriate caveats per Stage 5 of the competitive review recommendations.

### Session end state

- All computation is queued and will run unattended
- Paper writing not yet started (waiting for results)
- Remaining TODO before paper writing can begin:
  1. Verify chain completed (check squeue tomorrow)
  2. Confirm no NaN correlations in sw/ht/lo GEMBA
  3. Check direction_morphology_interaction.csv and domain_controlled_comparison.csv exist
  4. Check correlations.csv has all 10 metrics

## 2026-05-27 (Session 10 — OOM root cause, dwmatrix, competitive review triage)

### OOM root cause (jobs 11979541, then 12014894/12014573)

Job 11979541 (192G, dw partition) OOM'd at 5 min 10 sec — previously thought to be data
loading, but the diagnostic job 12014897 on dwmatrix proved it was model loading:
- Data loading: only 2.37 GB RSS total (MQM 1.13 GB, DA +1.24 GB, everything else ~0)
- xCOMET-XL load_from_checkpoint: spikes to **28.86 GB** (13 GB checkpoint + 13 GB tensors)
- `del model; gc.collect()`: RSS stays at 28.86 GB — Python does NOT return pages to OS,
  so MaxRSS accumulates across all sequentially loaded models without ever dropping.
- With 4 COMET models loaded one after another, peak RSS can reach 4 × ~14 GB = ~56 GB,
  but MaxRSS never resets, so SLURM saw 183 GB accumulated peak from 192 GB limit → OOM.

### Partition switch: dw → dwmatrix

`dw` partition had several blocking jobs ahead of ours (job IDs 11806491-11806497, 1b-chain-d).
`dwmatrix` is the matrix group's dedicated single node (dw-2-5, 2 TB RAM, 8× A100), always empty.
Switched both scripts to `--partition=dwmatrix`. Jobs started immediately.

### Memory fix: 192G → 512G

Nodes have 2 TB RAM. Previous 192 GB limit was unnecessarily conservative given accumulated
MaxRSS from sequential model loading. Bumped to 512 GB in run_comet.sh. With 512 G headroom,
all 4 COMET models (cumulative MaxRSS ≈ 56 GB) + Llama (≈ 16 GB) leave >400 GB margin.

### Current running job: 12014896 (dwmatrix, 512G, 28h)

Started 2026-05-27. Expected to complete ≈ 2026-05-28 (22h estimated runtime):
- xcomet (~3h), bleurt (~1h), kiwi22 (~1.5h), kiwi23 (~2h), GEMBA (~14h), analysis (~30min)
- GEMBA has crash-resume cache at results/gemba_cache.jsonl
- All 7 Tier 2 synthetic MQM caches exist; checkpoint properly skips bleu/chrf/bertscore/comet

### Competitive review triage (from claude_review.md)

**Done in code:**
- SPA (`soft_pairwise_accuracy`) = Deutsch et al. 2023 tie-calibrated accuracy ✓
- Direction × morphology interaction with eta-squared (`run_direction_morphology_interaction`) ✓
- Domain-controlled Ukrainian decomposition (`run_domain_controlled_comparison`) ✓
- Three-way direction split: x_to_en / en_to_x / pivot (de-fr, hi-bn, bn-hi, zu-xh, xh-zu) ✓
  — pivot category was NOT in the review; discovered by inspecting segment_ids
- WMT-year stratification (`analyze_tier_anomaly`) ✓
- Telegram claim scrubbed: WMT 2022 uk-en domain="other"/conversational (source unconfirmed) ✓
- Williams p stored as raw float (not rounded); "p≈0" underflow → paper should print p < 1e-300 ✓

**Blocked:**
- MetricX-24: no JAX/T5X, acknowledge in limitations section of paper
- Tier 2 human validation: needs ≥200 ESA-rated segments for 1 language (e.g. Swahili)
  — this is the single biggest reviewer objection; worth investing time before submission
- WMT23/24 MQM: HF dataset only goes to WMT22; justify as "all publicly available HF MQM data"

**Writing only (no code needed):**
- Title/abstract: lead with domain-not-resource finding
- Mondshine et al. contrast paragraph in related work
- Zouhar framing: "misread as low-resource problem"
- ITEM (Yari et al. 2025) citation
- WMT22 ceiling justification in data section

**Still open in code (low priority, post-results):**
- Russian ρ=0.157 anomaly investigation (reference quality check)
- p-value underflow display (paper-level, not pipeline)

## 2026-05-22 (Session 9 — OOM diagnosis, pipeline fixes, competitive assessment response)

### Root cause of OOM in job 11787744

Job 11787744 (submitted May 8) OOM'd at 7h14m. Root cause identified:
1. **Tier 2 generation ran for 7 hours** — sw/ht/lo loaded from cache, but th/my/am/ka each
   took ~1h47m on A100 (1012 segments × ~6.3s/seg at batch_size=4). All 4 completed and
   cache files were written: th (17:32), my (19:19), am (21:06), ka (22:53).
2. **Llama never freed after Tier 2 generation** — the `pipe` object went out of scope but
   Python GC hadn't reclaimed GPU/CPU RAM when `_run_metrics()` started loading xCOMET-XL.
   OOM'd 4 minutes after ka's cache file was written.
3. **Checkpoint skip was entirely broken** — `metrics_to_run` was never modified when loading
   from checkpoint, so every job recomputed bleu/chrf/bertscore/comet from scratch even when
   they were in the checkpoint. Silently wasted 3-4h per job.

### Fixes applied

**`src/mqmbench/pipeline.py`**:
- Fixed checkpoint skip bug: `metrics_to_run.remove(col)` for fully-loaded metrics
- Added `gc.collect()` after Tier 2 synthetic generation (+ `torch.cuda.empty_cache()`)
- Added `gc.collect()` after each heavy GPU metric (xcomet, bleurt, kiwi22, kiwi23)
- Added full GC + CUDA cache clear before GEMBA loads Llama
- GEMBA now passes a cache_file path so partial progress survives crashes
- Added `run_direction_morphology_interaction()` call, saves to direction_morphology_interaction.csv

**`src/mqmbench/data/synthetic_mqm.py`**:
- Explicit `del pipe; gc.collect(); torch.cuda.empty_cache()` after Tier 2 generation

**`src/mqmbench/metrics/gemba.py`**:
- Added `cache_file` parameter: reads partial results on startup, saves every 500 batches
- `return_full_text=False` to reduce output memory
- Progress logging every 1000 batches

**`src/mqmbench/analysis/correlation.py`**:
- Added `run_direction_morphology_interaction()`: 2×3 cells (direction × morphology type),
  per-cell mean Spearman r with bootstrap CIs over language-level values,
  and eta-squared effect sizes for direction, morphology, and interaction term.

**`scripts/slurm/run_comet.sh`**:
- time: 20:00:00 → 28:00:00; mem: 160G → 192G

### Job 11979541 (current, submitted 2026-05-22)

Expected timeline (all Tier 2 data cached; bleu/chrf/bertscore/comet properly skipped):
- Tier 2 load from cache: ~5 min
- xcomet (700k segs, bs=8, A100): ~3h
- bleurt (700k segs, bs=32): ~1h
- kiwi22 (700k segs, bs=16): ~1.5h
- kiwi23 XL (700k segs, bs=8): ~2h
- GEMBA (85k MQM segs, bs=4, Llama-8B): ~14h (cache at results/gemba_cache.jsonl)
- Analysis + plots: ~30 min
Total: ~22h (28h wall time → comfortable)

### Competitive assessment highlights + new code responses (2026-05-22)

- **Strongest contribution**: Ukrainian collapse is a domain confound (WMT22 uk-en domain="other"/
  conversational, the ONLY non-news/non-wiki language in our DA dataset). NOT from WMT24 Cs→Uk.
  The WMT24 Cs→Uk story (Charles Translator app, NOT Telegram) is separate literature context.
- **Direction asymmetry**: genuinely unclaimed in MT metric literature — now properly coded.
  Three-way split discovered in data: x_to_en / en_to_x / **pivot** (non-English pairs).
  Pivot: fr (de-fr), bn (hi-bn), hi (bn-hi), xh (zu-xh), zu (xh-zu) — completely off-domain
  for COMET-Kiwi source encoder. Previously incorrectly mapped to en_to_x.
  x_to_en: zh, uk, km, ps, gu, kk (he if data available). Previously only zh was correct.
- **TRANSLATION_DIRECTIONS bug fixed**: uk/km/ps/gu/kk were wrongly in en_to_x; pivot category
  added for de-fr/hi-bn/bn-hi/zu-xh/xh-zu pairs.
- **Domain-controlled comparison**: `run_domain_controlled_comparison()` added — the specific
  analysis the reviewer will demand: hold direction constant (x_to_en: uk/km/ps/gu/kk),
  vary domain (other vs wiki vs news) → shows domain drives uk's near-zero, not direction.
- **Direction × morphology interaction**: `run_direction_morphology_interaction()` added.
- **Morphology**: Mondshine et al. ACL 2025 (summarization, opposite COMET neural trend) — cite
- **SPA** already in our code = Deutsch et al. 2023 tie-calibrated accuracy; add citation
- **MetricX-24**: NOT in HF cache. Genuinely blocked without JAX/T5X setup. Acknowledge in limitations.
- **Telegram claim in research log**: corrected. WMT 2022 uk-en domain="other" is NOT confirmed
  as Telegram. Paper must say "domain='other'/conversational" only, with WMT 2022 Findings citation.
- **Tier 2 validation**: need human-annotated sample for ≥1 very-low-resource language (TODO)
- **EMNLP 2026** uses ARR; plan submission cycle accordingly
- **ITEM benchmark** (Yari et al. arXiv 2510.07061) — cite for Hindi medium > high anomaly

## 2026-05-08 (Session 8 continued — BLEURT, direction, morphology, length, rater agreement)

### Corrections to previous "blocked" assessments

- **BLEURT**: was wrongly called blocked. `Elron/bleurt-large-512` on HuggingFace is a
  PyTorch `BertForSequenceClassification` regression model — no TensorFlow needed.
  Implemented in `src/mqmbench/metrics/bleurt.py` and added to run list.
- **Morphological complexity**: was wrongly called blocked. Implemented as a lookup
  table (same pattern as `SCRIPT_TYPES`) — no external data needed.

### New additions

**BLEURT-large-512** (`src/mqmbench/metrics/bleurt.py`):
- BertForSequenceClassification regression model; takes (reference, hypothesis) order
- Output: approx. [-1, 2] (higher = better); pre-cached from `Elron/bleurt-large-512`
- Fills the "learned regression metric" gap alongside COMET; both are neural but BLEURT
  uses a BERT encoder trained on WMT rating data rather than a multilingual COMET backbone

**Translation direction analysis** (`run_direction_analysis`):
- Splits languages by WMT pair direction: x_to_en (zh-en, he-en) vs. en_to_x (everything else)
- Tests whether COMET/BERTScore trained on en→X data are less reliable for X→en evaluation
- Output: `direction_analysis.csv`, `plots/direction_analysis.png`

**Morphological type analysis** (`run_morphology_analysis`):
- Aggregates per-language correlations by morphological type (isolating / agglutinative / fusional)
- Key hypothesis: BLEU/ChrF hurt more on agglutinative languages (tr, fi, ka, ta) due to
  high type-to-token ratio; neural metrics should be more robust
- Output: `morphology_analysis.csv`, `plots/morphology_analysis.png`

**Sentence length analysis** (`run_length_analysis`):
- Bins segments: short (<10 tokens), medium (10–30), long (>30)
- Hypothesis: COMET/BERTScore degrade more on short segments (less semantic context)
  while BLEU degrades uniformly
- Output: `length_analysis.csv`, `plots/length_analysis.png`

**Inter-rater agreement analysis** (`run_rater_agreement_analysis`):
- Uses Google TSV `rater` column to compute per-segment fraction of raters who flagged error
- High agreement (all agree or all disagree) = clean signal; low = ambiguous
- Hypothesis: all metrics should be more reliable when raters agree
- Output: `rater_agreement_analysis.csv`, `plots/rater_agreement.png`

### Job 11787744 (replaces 11787616, 20h, 160G)
- Cancelled 11787616 mid-NLLB-translation to add new code
- FLORES+ for th/my/am/ka already cached; NLLB will rerun for new langs
- Checkpoint preserved: bleu/chrf/bertscore/comet for 702k rows
- New metrics to compute: bleurt, xcomet, cometkiwi, cometkiwi23, gemba, ensemble

### Full paper experiment list (when job completes)
- 32 languages, 12 families, 4 script types, 3 morphological types, 2 directions
- 10 metrics + ensemble: BLEU, ChrF, BLEURT, BERTScore, COMET, xCOMET-XL,
  Kiwi-22, Kiwi-23-XL, GEMBA, Ensemble
- Analyses: segment-level, system-level, domain, direction, morphology, length,
  rater agreement, reference quality, inter-metric correlation, score distributions,
  category (accuracy/fluency), tier anomaly, Williams tests, bootstrap CIs, SPA

---

## 2026-05-08 (Session 8 continued — five new analyses added)

### What we added

**System-level correlation** (`run_system_level_analysis`):
- Aggregates per-(lang, system) mean scores, then correlates system rankings with human quality
- Standard WMT Metrics Shared Task primary measure; expected by every reviewer
- System-level Spearman r is typically 0.8–0.95 vs. segment-level 0.2–0.5
- The gap itself is a finding: metrics rank systems well but score individual translations poorly
- Requires `system` column — present in MQM data; DA data may be skipped gracefully
- Output: `results/system_level_correlations.csv`, `plots/system_vs_segment.png`

**Inter-metric correlation matrix** (`compute_metric_correlations`):
- Pairwise Spearman r between all 9 metrics (pooled across all segments)
- High values = redundant; low = complementary signal
- Justifies metric selection and motivates the ensemble
- Output: `results/metric_correlation_matrix.csv`, `plots/metric_correlation_matrix.png`

**Score distribution plot** (`plot_score_distributions`):
- Violin plot of raw metric scores split by resource tier
- Narrow violin = metric collapses scores for that tier (low variance = low discrimination)
- Expected finding: BLEU/ChrF should show narrower distributions for low-resource
- Output: `plots/score_distributions.png`

**Reference quality effect** (`reference_quality_effect`):
- Computes Kiwi advantage (Kiwi Spearman r − COMET Spearman r) per (lang, annotation_tier)
- Tests: does Kiwi gain more over COMET when references are crowd-sourced (DA) vs. professional (MQM)?
- If yes, supports the hypothesis that reference quality drives the Kiwi-vs-COMET story
- Output: `results/reference_quality_effect.csv`, `plots/reference_quality_effect.png`

**Ensemble meta-metric** (computed in `_run_metrics`):
- Average of all available neural metrics: comet, xcomet, xcometxxl, cometkiwi, cometkiwi23
- Computed post-GPU with zero extra cost; often outperforms any individual metric
- Included in all downstream analyses as metric `"ensemble"`

### Job 11787100 (replaces 11784597, 20h)
- Will resume from checkpoint: bleu/chrf/bertscore/comet already done (702k rows)
- New metrics: xcomet, xcometxxl, cometkiwi, cometkiwi23, gemba, ensemble
- New outputs: 4 additional CSV files, 5 additional plots

### What the paper has when this completes
- 32 languages, 12 families, 4 script types, 3 annotation tiers
- 10 metrics (9 individual + ensemble): BLEU, ChrF, BERTScore, COMET, xCOMET-XL, xCOMET-XXL, Kiwi-22, Kiwi-23-XL, GEMBA, Ensemble
- Segment-level AND system-level correlations (standard WMT table)
- Domain-controlled analysis (news vs. conversational)
- Reference quality controlled analysis (MQM professional vs. DA crowd)
- Score distribution diagnostics
- Inter-metric redundancy map
- Williams tests, bootstrap CIs, SPA, accuracy/fluency category breakdown

This is a complete paper. The only remaining gaps are MetricX (blocked), human Tier 2 validation (requires humans), and writing.

---

## 2026-05-08 (Session 8 — domain analysis, CI bands, GEMBA, encoder cache fix)

### What we did

**Root-caused job 11552886 failure:**
- xCOMET-XL and xCOMET-XXL use `facebook/xlm-roberta-xl` / `facebook/xlm-roberta-xxl` as their encoders
- With `HF_HUB_OFFLINE=1`, the tokenizer vocabulary file couldn't load even though the checkpoint was cached
- Fix: ran `snapshot_download('facebook/xlm-roberta-xl')` and `snapshot_download('facebook/xlm-roberta-xxl')` on the login node
- Same applies to wmt23-cometkiwi-da-xl (also uses xlm-roberta-xl)
- Checkpoint from the failed job preserved: bleu, chrf, bertscore, comet across 702,970 rows with segment_id — will be used for resume

**Domain-stratified analysis — new:**
- `run_domain_analysis()` in `correlation.py`: groups `(lang, domain)` from `scores_df` and runs `correlate_metric_vs_human()` within each domain separately
- Minimum 30 segments per group to ensure stable correlation estimates
- Returns same schema as `run_correlation_analysis()` plus `domain` column
- Saves to `results/domain_analysis.csv`
- `plot_domain_analysis()`: grouped bar chart (news vs. other), SD error bars, one panel per measure
- This turns the Ukrainian domain confound into a paper-strength finding: "within-domain, metric reliability is consistent; pooling across domains depresses correlations for languages evaluated on non-news text"

**CI bands on main plots:**
- `plot_correlation_by_resource_level()`: switched y-axis from Kendall τ to Spearman ρ (reviewers expect it; more intuitive); added `errorbar="sd"` (±1 SD across languages in tier); added `stripplot` overlay showing individual language points
- `plot_correlation_by_script_type()`: same upgrades
- `plot_kiwi_vs_comet_by_tier()`: 95% bootstrap CI error bars per language point (using `spearman_ci_lo`/`spearman_ci_hi` from `corr_df`); handles kiwi22 vs. kiwi23 in a multi-row grid

**GEMBA-MQM as evaluated metric — enabled:**
- `run_gemba = true` in settings.toml (Llama-3.1-8B-Instruct already cached from Session 5)
- Circular evaluation exclusion already in place: GEMBA scores on `synthetic_mqm` tier are dropped from `correlations.csv` before analysis
- Adds LLM-as-judge to the metric comparison (BLEU/ChrF → BERTScore → COMET-family → GEMBA)

**Job 11784597 submitted (20h):**
- Will resume from checkpoint (bleu/chrf/bertscore/comet already done; 702k rows)
- New metrics to compute: xcomet, xcometxxl, cometkiwi, cometkiwi23, gemba
- New output files: `domain_analysis.csv`, updated plots with CI bands

### What the paper now has when this job completes
- 32 languages, 12 families, 4 script types, 3 annotation tiers
- 9 metrics: BLEU, ChrF, BERTScore, COMET, xCOMET-XL, xCOMET-XXL, Kiwi-22, Kiwi-23, GEMBA
- All correlation measures: Pearson, Spearman, Kendall τ, pairwise accuracy, SPA
- Williams significance tests, bootstrap 95% CIs
- Accuracy vs. fluency category breakdown (de, zh, he, es spans)
- Domain-controlled analysis (news vs. other)
- COMET-Kiwi 2022 vs 2023 temporal comparison

### Next after job completes
- Verify domain_analysis.csv shows the expected pattern (uk much lower in "other" domain than in "news")
- Check if GEMBA lands between BERTScore and COMET as expected for high-resource, or closer to surface metrics for low-resource
- Start writing the paper

---

## 2026-04-21 (Session 7 — Tier 2 expansion, xCOMET, checkpoint fix)

### What we did

**Tier 2 language expansion (+4 languages → now 32 total):**
- Added Thai (`th`), Burmese (`my`), Amharic (`am`), Georgian (`ka`) to `tier2_langs` in settings.toml
- All four supported by FLORES+/NLLB-200 with confirmed BCP-47 codes: `tha_Thai`, `mya_Mymr`, `amh_Ethi`, `kat_Geor`
- Added to `resource_tiers.low` and updated language family/script type maps in both settings.toml and correlation.py:
  - tai_kadai now includes `th` (same family as `lo`)
  - sino_tibetan now includes `my` (Tibeto-Burman branch)
  - afro_asiatic now includes `am` (Semitic, alongside `he`)
  - New family: `kartvelian = ["ka"]` — Georgian is its own unique family
  - Script assignments: th/my/am → abugida; ka → alphabetic (Georgian unique alphabet)
- BCP-47 entries added to `data/utils.py` ISO_TO_BCP47 dict

**He-en (WMT23) and en-es (WMT24) span TSVs — activated automatically:**
- Confirmed TSVs exist: `generalMT2023/heen/mqm_generalMT2023_heen.tsv` and `generalMT2024/mqm_generalMT2024_enes.tsv`
- `_LANG_FROM_FILENAME` in `wmt_mqm.py` already maps `heen → he` and `enes → es`
- These files load automatically since `wmt_mqm_span_dir` points to the right place — no code change needed
- Adds Hebrew and Spanish span-level category data to accuracy vs. fluency analysis (previously only de/zh)

**xCOMET-XL enabled:**
- Added `"xcomet"` to `metrics.run` in settings.toml (was commented out pending access)
- Obtained gated access to `Unbabel/XCOMET-XL` — pre-downloaded via `snapshot_download()`
- xCOMET is a larger reference-based COMET that uses xCOMET's multi-head scoring architecture

**Checkpoint fix — segment_id based merge:**
- Bug: checkpoint resume used positional assignment (`scores_df[cols] = ckpt[cols].values`) which breaks when new Tier 2 languages change the row count
- Fix: `_run_metrics()` now merges checkpoint by `segment_id` (left join); metrics with any NaN rows (new languages) are dropped from the skip list and recomputed
- `_checkpoint()` now saves `segment_id` alongside `lang` and `annotation_tier` for future partial resumes
- Old checkpoint (without segment_id) deleted before resubmission

**SLURM job 11552831 submitted:**
- Time limit bumped to 16h (COMET + xCOMET-XL + COMET-Kiwi across 32 languages)
- Replaces cancelled job 11552619 (had 12h limit with old settings)
- Will compute all 6 metrics from scratch (old checkpoint deleted due to no segment_id)

**MetricX-23 and BLEURT-20 — blocked:**
- MetricX-23: Google's pip-installable package (`metricx`) was a name squatter; GitHub repo has no setup.py; direct HuggingFace approach risky without confirmed input format
- BLEURT-20: requires TensorFlow (not installed, not practical to add)
- Decision: xCOMET-XL covers the "strong neural metric" gap; MetricX left for future work

### Publishability status (updated)
- **32 languages**, 12 families, 4 script types — broader than any published MT metric meta-eval
- **Metrics**: BLEU, ChrF, BERTScore, COMET, xCOMET-XL, COMET-Kiwi (6 metrics, covers reference-based + reference-free + multi-head categories)
- **Category correlation**: now includes Hebrew and Spanish spans (previously only de/zh)
- **Job 11552831 pending** — awaiting GPU allocation

### Questions for advisor
- Georgian and Amharic: both abugidas but from completely different script origins (Ge'ez vs. Brahmic). Worth noting in script type section that "abugida" is a structural property, not a genetic one?
- xCOMET vs. COMET on medium-resource: expect xCOMET to win, but will the gap be larger for morphologically complex languages?

---

## 2026-04-15 (Session 6 — Publishability upgrades)

### What we did

**Language expansion (13 → 28 languages, all zero new data collection):**
- Added 15 languages to `wmt_da_target_langs` in settings.toml: fr, pl, fi, et, is, lt, lv, bn, hi, gu, ta, ja, kk, xh, zu
- All come from `RicardoRei/wmt-da-human-evaluation` (already loaded), so no additional download needed
- Updated `resource_tiers.medium` to include all new DA languages
- Added 3 new language families: dravidian (ta), japonic (ja), uralic (fi, et)
- Expanded `LANGUAGE_FAMILIES`, `SCRIPT_TYPES`, `RESOURCE_TIERS` in both settings.toml and correlation.py
- New script type assignments: ja → logographic; bn/hi/gu/ta → abugida; rest → alphabetic

**Soft Pairwise Accuracy (SPA) — WMT 2024 primary measure:**
- Implemented `soft_pairwise_accuracy()` in correlation.py
- Difference from existing pairwise_accuracy: metric-tied pairs contribute 0.5 instead of being excluded; only human-tied pairs are excluded
- `correlate_metric_vs_human()` now returns both `pairwise_acc` and `spa`
- Added `"spa"` to `_SUMMARY_COLS`, result DataFrame columns, and all summary tables

**COMET-Kiwi enabled and compared:**
- Added `"cometkiwi"` to `metrics.run` in settings.toml (was blocked by HF offline; weights now pre-downloaded)
- Added `kiwi_vs_comet_by_tier()` in correlation.py: compares reference-free Kiwi vs. reference-based COMET per language across spearman_r, pairwise_acc, spa
- Output: `results/kiwi_vs_comet.csv`
- Added `plot_kiwi_vs_comet_by_tier()` in plots.py: scatter with equal-performance diagonal, points labelled by language, coloured by tier
- Key research question: do low-resource pairs (where references may be noisy) benefit from dropping the reference?

**Accuracy vs. fluency category correlation — activated:**
- `wmt_mqm_span_dir = "../wmt-mqm-human-evaluation"` was already set; TSVs confirmed present
- No code changes needed; pipeline already checks this path and runs `run_category_correlation()` if found
- Output: `results/category_correlations.csv` + `results/plots/category_heatmap.png`

**Medium > High anomaly controlled analysis:**
- Added `year` and `system` to keep list in `load_wmt_mqm()` so scores_df carries WMT year
- Added `analyze_tier_anomaly()` in correlation.py: groups by (lang, year) for MQM data, computes per-year Spearman r, compares cross-year variance between high/medium tiers
- Hypothesis: high-resource languages span WMT 2020–2024 with shifting domains and system populations → high cross-year variance → depressed aggregate correlation
- Output: `results/tier_anomaly.csv`
- Added `plot_tier_anomaly()`: left panel = per-year lines for high-resource langs; right panel = mean vs. std scatter showing which tier has more heterogeneity
- Also added `plot_kiwi_comparison()` and `plot_anomaly()` to `scripts/make_presentation_plots.py`

**Pipeline/plot updates:**
- `pipeline.py` now imports and calls kiwi_vs_comet_by_tier, analyze_tier_anomaly; saves to new CSVs; generates kiwi_vs_comet.png and tier_anomaly.png
- `make_presentation_plots.py`: updated pipeline diagram (28 languages, 11 families; SPA in measures list); added Figure 4 (Kiwi vs COMET) and Figure 5 (anomaly)
- SLURM time limit bumped to 12h (more languages + cometkiwi); output redirected to logs/

**SLURM job submitted:**
- Job **11505606** on `dw-2-4` (matrix/dw partition, 1 GPU, 128G)
- Expected: BLEU + ChrF + BERTScore + COMET + COMET-Kiwi across 28 languages (~10h)
- Output: `logs/mqmbench_comet_11505606.out`

### New outputs when job completes
- `results/correlations.csv` — expanded to 28 languages × 5 metrics; now includes `spa` column
- `results/kiwi_vs_comet.csv` — Kiwi vs. COMET comparison per language
- `results/tier_anomaly.csv` — per-year Spearman r for multi-year languages
- `results/category_correlations.csv` — accuracy vs. fluency breakdown (MQM tier only)
- `results/plots/kiwi_vs_comet.png`
- `results/plots/tier_anomaly.png`
- `results/plots/presentation_kiwi_vs_comet.png`
- `results/plots/presentation_tier_anomaly.png`

### Publishability status (updated)
- Language coverage: **28 languages**, 11 families, 4 script types — no published study spans this breadth
- Metrics: BLEU, ChrF, BERTScore, COMET, COMET-Kiwi (SPA now primary measure, matching WMT 2024)
- Category correlation pending (code+data ready; activates on this pipeline run)
- Kiwi vs. COMET by resource tier is the key new analytical table for paper strengthening
- Tier anomaly analysis provides the controlled explanation reviewers will ask for
- Next gap: MetricX-23 / BLEURT-20 (requires separate installs); human validation of Tier 2 for 2–3 langs

### Questions for advisor
- Is the SPA formula (tied metric = 0.5) exactly what Thompson et al. 2024 use, or does it include additional tie-calibration steps?
- For the kiwi vs. COMET result: if Kiwi wins on low-resource but loses on high-resource, is the practical recommendation "use Kiwi when references are from a single translator"?



## 2026-04-12 (Session 5, 9AM–5PM+)

### What we did

**CUDA debugging resolved** (carried over from Apr 10):
- Root cause: `torch 2.11.0+cu130` requires CUDA 13.0; all cluster nodes max at CUDA 12.8
- Fix: pinned `torch` to cu124 wheel via `pyproject.toml` uv index source; added `setuptools==69.5.1` to core deps to fix `pkg_resources` breakage from `setuptools>=72`
- cuDNN/NCCL missing after cu124 install → fixed with `uv pip install nvidia-cudnn-cu12 nvidia-nccl-cu12`
- First successful full pipeline run: job 11463513 on m13l, 39 minutes, BLEU/ChrF/BERTScore/COMET results for all tiers

**Bootstrap confidence intervals**:
- Added `_bootstrap_ci()` (percentile method, 1000 resamples, seed=42) to `correlation.py`
- `correlate_metric_vs_human()` now computes `spearman_ci_lo` / `spearman_ci_hi`; columns added to `run_correlation_analysis()` output and `correlations.csv`

**Tier 2 all-no_error fix**:
- Old GEMBA-MQM prompt caused Llama-3.1-8B to rate 100% of sw/ht/lo translations as NO ERRORS → quality_score=1.0 for all segments → NaN correlation (zero variance)
- New prompt: few-shot examples with actual errors force more critical evaluation
- Deleted stale cache files; queued chained jobs: 11465030 (synth re-annotation) → 11465038 (full pipeline)

**xCOMET added**:
- `settings.toml` `run` list now includes `"xcomet"`
- `run_comet.sh` time limit bumped to 8h; xCOMET-XL will run as part of job 11465038

**GEMBA circular evaluation fix**:
- Added filter in `pipeline.py`: GEMBA metric correlations on `synthetic_mqm` tier are excluded from `correlations.csv` (same model annotates and evaluates → circular)
- Logged with explanation; results for Tier 1a/1b unaffected

**Span-level category correlation (accuracy vs. fluency)**:
- Added `load_wmt_mqm_spans()` to `wmt_mqm.py` — reads Google's raw WMT MQM TSV files
- `pipeline.py` checks `settings.data.wmt_mqm_span_dir`; if set and directory exists, loads spans and runs `run_category_correlation()`
- Falls back gracefully if TSV dir is not present
- To activate: download TSVs from github.com/google/wmt-mqm-human-evaluation, set `wmt_mqm_span_dir = "data/wmt_mqm_spans"` in settings.toml

**Late session additions (9PM+)**:
- Added COMET-Kiwi (`Unbabel/wmt22-cometkiwi-da`) as reference-free metric — addresses key gap flagged in literature (reference quality unreliable for low-resource languages); model downloaded, wired into pipeline and settings
- Added pairwise accuracy to `correlate_metric_vs_human()` — WMT 2023-2024 primary segment-level meta-evaluation measure; included in `correlations.csv` and all summary tables
- Added Williams (1959) test (`williams_test()`, `run_williams_tests()`) — significance test for difference between two correlated correlations sharing a human criterion; outputs `williams_tests.csv` comparing each metric vs. COMET per language
- Added error analysis (`analyze_metric_disagreements()`) — identifies top-50 worst-disagreement segments per (lang, metric) by rank residual; outputs `metric_disagreements.csv` with source text, scores, and over/under-scored direction
- Jobs resubmitted on `m13h` (H200, idle) with `--qos=normal` after `cs/matrix` was blocked and estimated start was 6:45AM tomorrow; synth job running as of ~9:40PM
- Cloned `google/wmt-mqm-human-evaluation` TSV span data; loader working (641k span rows for de/zh/es/he); Russian TSV malformed upstream (trailing tab shifts JSON into severity column — not our bug)

### Results from job 11463513 (pre-Tier-2 fix)
- COMET dominated all tiers (Spearman 0.6–0.8 for high/medium resource)
- ChrF consistently outperformed BLEU
- Ukrainian: near-zero across ALL metrics (confirmed domain confound — WMT 2022 uk-en domain="other", conversational/non-news, not news like all other DA languages)
- Tier 2 (sw/ht/lo): all NaN — fixed with prompt update, awaiting rerun

### Jobs queued
- **11465030** (`mqmbench_synth`, dw): re-annotate sw/ht/lo with fixed prompt
- **11465038** (`mqmbench_comet`, dw, `afterok:11465030`): full pipeline with xCOMET

### Publishability status
- Core results (Tier 1a/1b, 4 metrics, 11 languages) are solid and reportable
- Bootstrap CIs now support statistical claims
- Tier 2 fix pending (jobs queued)
- Category correlation (accuracy vs. fluency): code complete, needs WMT span TSV download
- Ukrainian domain confound should be called out explicitly in the paper

### Future work (to strengthen toward publication)

**Short-term (would improve WMT/LREC-COLING submission):**
- MetricX-23 and BLEURT-20 — reviewers expect these; requires separate library installs and model downloads
- Soft Pairwise Accuracy (SPA) — stricter WMT 2024 variant of pairwise accuracy with tie calibration; pairwise accuracy is close but SPA is the exact official measure
- Validate Tier 2 synthetic annotations: even 200 human judgments on sw/ht/lo would transform "synthetic" into "validated synthetic"
- Accuracy vs. fluency category correlation — code complete; needs raw WMT span TSVs already downloaded; just set `wmt_mqm_span_dir` and re-run
- Russian span data — the 2022 enru TSV is malformed (trailing tab); could fetch the 2021 or 2023 version manually

**Medium-term (EMNLP Findings territory):**
- Reference-free vs. reference-based comparison by resource tier — is COMET-Kiwi competitive with COMET when references are low-quality? This is the practical payoff of adding Kiwi.
- Adapt a metric for low-resource: fine-tune COMET on synthetic MQM annotations for sw/ht/lo and test if it improves — would add the constructive element reviewers want
- Expand language coverage: Thai (abugida, no word boundaries), Myanmar (abugida), Amharic (Ge'ez script) — would strengthen the script-type story
- Quantify medium > high anomaly: test whether it disappears when controlling for number of WMT years and MT systems — would turn a finding into a methodological insight

**Framing note:** strongest submission angle is "what drives MT metric reliability across typologically diverse languages?" — diagnostic study + recommendation matrix, not pure negative result. COMET-Kiwi vs. COMET by resource tier is the key table to build that recommendation.

**Language expansion — zero new data collection needed:**

*From WMT DA (`RicardoRei/wmt-da-human-evaluation`) — already loaded, just add to `wmt_da_target_langs`:*
| Code | Language | Family | Script | Why interesting |
|------|----------|--------|--------|-----------------|
| bn | Bengali | Indo-European | Abugida (Bengali) | Large language, underrepresented in meta-eval |
| gu | Gujarati | Indo-European | Abugida (Gujarati) | Brahmic script variant |
| hi | Hindi | Indo-European | Abugida (Devanagari) | Huge speaker population, shared script with many languages |
| ta | Tamil | Dravidian | Abugida (Tamil) | Non-Indo-European, distinct script |
| ja | Japanese | Japonic | Logographic+syllabic | Mixed script (kanji+kana), no spaces |
| kk | Kazakh | Turkic | Cyrillic | Expands Turkic family beyond tr |
| xh | Xhosa | Niger-Congo | Latin | Click consonants, Bantu |
| zu | Zulu | Niger-Congo | Latin | Click consonants, Bantu, closely related to xh |
| et | Estonian | Uralic | Latin | Agglutinative, non-Indo-European |
| fi | Finnish | Uralic | Latin | Agglutinative, highly inflected |
| is | Icelandic | Indo-European | Latin | Low-resource, heavily inflected Germanic |
| lt | Lithuanian | Indo-European | Latin | Most archaic living IE language |
| lv | Latvian | Indo-European | Latin | Baltic, sibling of Lithuanian |
| pl | Polish | Indo-European | Latin | Slavic with complex morphology |
| fr | French | Indo-European | Latin | High-resource, useful sanity check |

*From FLORES+ + NLLB-200 (Tier 2, synthetic only — just add language codes to `tier2_langs`):*
| Code | Language | Family | Script | Why interesting |
|------|----------|--------|--------|-----------------|
| tha_Thai | Thai | Tai-Kadai | Thai | No word boundaries, same family as lo |
| mya_Mymr | Burmese | Sino-Tibetan | Myanmar (abugida) | Unique script, very low resource |
| amh_Ethi | Amharic | Afro-Asiatic | Ge'ez (unique) | Only Ge'ez script language in dataset |
| yor_Latn | Yoruba | Niger-Congo | Latin | Tonal, W. African, low resource |
| ibo_Latn | Igbo | Niger-Congo | Latin | Tonal, W. African, low resource |
| kat_Geor | Georgian | Language isolate | Georgian (unique) | Script isolate, no known relatives |
| hye_Armn | Armenian | Indo-European | Armenian (unique) | Unique script, IE outlier |
| uig_Arab | Uyghur | Turkic | Arabic (RTL) | Turkic in Arabic script — tests script vs. family |
| tel_Telu | Telugu | Dravidian | Abugida (Telugu) | Expands Dravidian beyond Tamil |
| kan_Knda | Kannada | Dravidian | Abugida (Kannada) | Expands Dravidian coverage |
| eus_Latn | Basque | Language isolate | Latin | Only language isolate with Latin script in the set |
| bod_Tibt | Tibetan | Sino-Tibetan | Tibetan (abugida) | Brahmic-derived, very low resource |

---

## 2026-04-06 (Session 3, 9–11PM)

### What we did
- **Diagnosed SLURM timeout**: Job 11262595 ran 4 hours on CPU — CUDA driver on m9g nodes (version 12080) incompatible with `torch 2.11.0+cu130`. PyTorch silently fell back to CPU; NLLB on CPU is ~2h/language.
- **Fixed SLURM scripts**: All three (`run_nllb.sh`, `run_synthetic_mqm.sh`, `run_comet.sh`) now use `--partition=dw --qos=matrix` (A100). `m13l` partition has the same driver issue.
- **Resubmitted**: Job 11304485 on `m13l` (sw + ht already cached from timeout run; only `lo` ~1012 segments remains, ~2h to complete).
- **Root-caused Ukrainian near-zero correlation**: Spearman r=0.010 (p=0.19), confirmed independent of normalization choice. Cause: WMT 2022 uk-en data is domain "other" (conversational/non-news text, avg 12 words/sentence) vs. "news" for all other DA languages. BLEU/ChrF surface overlap with a single reference is a poor proxy for quality in conversational text with many valid paraphrases. This is a domain confound, not a language/script effect. NOTE: the source of WMT 2022 uk-en "other" domain is not confirmed as Telegram — this claim must NOT appear in the paper without a citation to the WMT 2022 Findings paper. Refer to it as domain="other" (conversational).
- **Added `domain` column** to `wmt_da.py`, `wmt_mqm.py`, and `run_correlation_analysis()` output so domain effects are visible in `correlations.csv`.
- **11/11 tests still pass** after correlation.py changes.

### Key finding: Ukrainian is a domain outlier
All other languages are evaluated on **news** text. Ukrainian WMT 2022 was collected from conversational sources (domain="other"). This means the alphabetic/Indo-European averages in Dr. Fulda's analysis are confounded by domain. Should be flagged in the paper — Ukrainian may need to be treated separately or excluded from family/script aggregations.

### SLURM status
- 11304485 (synthetic, m13l): RUNNING as of session end — will finish lo translation (~2h) then synthetic MQM scoring
- Next: once 11304485 completes, `sbatch scripts/slurm/run_comet.sh` (dw/matrix) for BERTScore/COMET/xCOMET

---

## 2026-04-06 (Session 2)

### What we did
- Fixed language family/script classification bugs: `he` moved to `afro_asiatic`, `ps` moved out of `afro_asiatic` (it's Indo-European/Iranian), `ha` moved out of `niger_congo` (it's Afro-Asiatic/Chadic), `lo` moved from `alphabetic` to `abugida` (Lao is Brahmic-derived like Khmer). Fixed in both `correlation.py` and `settings.toml`.
- Added `tier2_langs = ["sw", "ht", "lo"]` to settings.toml and updated pipeline.py to use it. Previously, Tier 2 FLORES/NLLB was running on all 6 low-resource langs (ha/km/ps unnecessarily, since they have DA data).
- Fixed SLURM scripts: `mamba activate` → `$SLURM_SUBMIT_DIR` + `.venv/bin/python` (old scripts failed with exit code 127)
- Fixed `_text_lists()` in pipeline.py: NaN values in text columns caused TypeError in sacrebleu
- Pre-downloaded NLLB-200 and Llama-3.1-8B weights on login node (network available)
- Submitted SLURM jobs: 11262595 (NLLB), 11262605 (synthetic, dependency)
- **Full login-node pipeline run succeeded**: 150,347 MQM segments (de/ru/zh) + 220,987 DA segments (cs/ha/km/ps/tr/uk) = 371,334 segments total

### First results (BLEU + ChrF, 9 languages)

Notable findings:
- **ChrF consistently outperforms BLEU** across all script types and families
- **Abugida scripts (km, lo)** show highest metric correlation (ChrF r=0.38) — counterintuitive relative to Dr. Fulda's hypothesis; may reflect km/lo having fewer segments (4.7k each) rather than script effects
- **Ukrainian (uk)** near-zero correlation for both metrics — suspicious; could be annotation noise, domain mismatch, or genuinely poor metric performance. Worth investigating separately.
- **Russian (ru)** BLEU correlation negative (-0.04) — unusually low compared to de (0.15) and zh (0.15)
- **Medium tier** outperforms high tier for both metrics — likely because high tier (de/ru/zh) spans multiple WMT years/domains with more variance

### SLURM job status
- 11262595 (run_nllb.sh): Pending/Running as of session end
- 11262605 (run_synthetic_mqm.sh): Pending, depends on 11262595

---

## 2026-04-06 (Session 1)

### What we did
- **Wired Dr. Fulda's analysis into pipeline.py**: Added calls to `summarize_by_script()`, `summarize_by_family()`, `plot_correlation_by_script_type()`, and `plot_correlation_by_language_family()` in `run_pipeline()`. Results saved to `script_type_summary.csv`, `family_summary.csv`, and the corresponding PNG plots.
- **Installed pytest** (was missing from venv): `uv pip install pytest`
- **Confirmed 11/11 unit tests pass** (`tests/test_converter.py`)
- **Smoke test (Tiers 1a + 1b)**: Confirmed working end-to-end on login node:
  - Tier 1a WMT MQM: 49,741 segments loaded for `de` ✓
  - Tier 1b WMT DA: 135,844 segments loaded for `cs` ✓
  - Tier 2 NLLB translation killed by login node CPU time limit (expected — belongs on SLURM)

### Key findings
- WMT DA has more languages than originally thought: `['bn', 'cs', 'de', 'et', 'fi', 'fr', 'gu', 'ha', 'hi', 'is', 'ja', 'kk', 'km', 'lt', 'lv', 'pl', 'ps', 'ru', 'ta', 'tr', 'uk', 'xh', 'zh', 'zu']` — future work could expand DA coverage further
- NLLB translation runs on CPU only on login node (no usable GPU); **must run `run_nllb.sh` via SLURM** for Tier 2 data generation

### Next steps
1. **Submit SLURM jobs** for Tier 2 data generation:
   - `sbatch scripts/slurm/run_nllb.sh` — translate FLORES+ for low-resource langs (sw, ht, lo)
   - `sbatch scripts/slurm/run_synthetic_mqm.sh` — LLM-annotate with GEMBA-MQM style prompting
2. **Run full pipeline** after caches are populated (BLEU + ChrF first, then add BERTScore/COMET on GPU)
3. **Update README** — reflect expanded language set (13 langs), script/family analysis dimensions, Dr. Fulda's research questions

---

## 2026-04-05

### What we did
- Full pivot from private LDS corpus to public data sources
- Rewrote data loaders: `wmt_mqm.py`, `wmt_da.py`, `flores.py`, `nllb.py`, `synthetic_mqm.py`
- Added `data/utils.py` (shared ISO→BCP47 map, JSONL cache helpers, WMT column renaming)
- Added `constants.py` with `AnnotationTier` class
- Rewrote `pipeline.py` for three-tier loading sequence
- Added language family and script type analysis to `correlation.py` and `plots.py` (Dr. Fulda's feedback)
- Expanded language set to 13 languages across 3 resource tiers
- Created SLURM scripts for GPU jobs

### Key discoveries
- `RicardoRei/wmt-mqm-human-evaluation` is sentence-level aggregated scores only (no spans/categories) — category analysis disabled until span data is available
- `facebook/flores` broken in modern datasets library — switched to `openlanguagedata/flores_plus`
- hr/ro not in WMT DA — replaced with cs/tr
- he-en not in MQM dataset — skipped gracefully


## 2026-09-29 — Post-publication validity audit (independent recomputation, not pipeline outputs)

Motivation: user has had 3 projects in a row where findings turned out false after major bugs; prior audits in this project only checked pipeline outputs against themselves.

**Ruled out:**
- *Positional-join misalignment in all DA data.* Every DA number joins scores_{metric}.csv to DA rows by position (segment_id is a non-unique domain key). Recomputed sentence chrF++ from each DA row's own hypothesis/reference at 3,000 random positions per language: Spearman vs. checkpoint = 1.0000 for all 21 DA languages, identical row counts; shuffled control ~0. (`scripts/audit/audit_da_alignment.py`, `results/audit_da_alignment.csv`)
- *Year/system-pool confound for the direction gap.* Same-language, same-WMT-year cells with both directions (n=19): en->X > X->en for COMET in 19/19 (mean +0.287), MetricX 19/19, CK23 19/19, chrF 18/19, BLEU 16/19. (`scripts/audit/audit_direction_confounds.py`, `results/audit_direction_by_year.csv`)

**Found — interpretive, threatens the headline claim:**
- *The direction gap is in metric-HUMAN agreement, not metric behavior.* Same-year matched cells: COMET~MetricX agreement 0.834 (en->X) vs 0.817 (X->en), COMET~CK23 0.848 vs 0.814, COMET~chrF 0.584 vs 0.629 — flat. COMET~human 0.665 vs 0.378. Metrics agree with each other equally in both directions; only agreement with the X->en human labels drops.
- *X->en human labels degrade monotonically by year, for every metric incl. BLEU:* COMET~human 2017 ~0.57-0.69, 2018 ~0.47-0.57, 2019 ~0.40-0.52, 2020 ~0.25-0.36, 2021 ~0 (cs -0.006, ja 0.029, is 0.067, ha 0.045), 2022 ~0.07-0.15 — while COMET~MetricX stays 0.63-0.89. WMT21 into-English DA was reference-based crowd-worker DA; out-of-English was translators/researchers (WMT21 findings, aclanthology 2021.wmt-1.1).
- *Ukrainian "domain confound" not supported:* uk-en 2022 rho=0.001, but cs-en 2022 (mostly news) = 0.066 and ja-en 2022 = 0.146 — news-domain WMT22 into-English data is also near zero. Ukrainian looks like WMT22 into-English label quality, not domain. Same for is-en/ha-en ("annotation noise" is right but it's the whole WMT21 X->en release, incl. cs-en and ja-en). Table 5's "complete metric failure in 2021" for cs-en is the same artifact.
- Better-supported reading of the headline: direction predicts metric agreement with WMT DA labels, and the drop traces to into-English human annotation, not metric reliability. Practitioner recommendations built on X->en metric rankings (CK23 vs COMET etc.) rest on correlations with degraded labels.

**Found — unaddressed methodology:** COMET-22, CometKiwi, xCOMET, MetricX were trained on WMT DA labels overlapping the evaluation years; the paper never discusses train/test overlap. BLEU/chrF show the same year decline, so contamination isn't the driver of the direction trend, but it bears on neural-vs-surface magnitudes.

**Found — reproducibility bug:** uncommitted change to build_segment_id appends `_N` suffixes; checkpoints hold old IDs, so rerunning analyze_direction_separated.py today inner-joins zero rows. Published Tables 2/8/LOO (from the Sep 5 run) are correct but not regenerable from current code.

**Open:** can't yet distinguish "noisy crowd labels" from "misaligned labels inside the upstream HF dataset" for 2021/2022 X->en; a system-level check against WMT official rankings would discriminate. MQM tier (uniform professional protocol) shows no direction effect (he-en .713, zh-en .447 vs en-de .425, en-ru .157, en-es .586), n far too small to conclude.

### 2026-09-29 (cont.) — Open question resolved: noisy vs. misaligned X->en labels

- **HF dataset is faithful, not misaligned.** Joined RicardoRei/wmt-da-human-evaluation to WMT's official mt-metrics-eval-v2 segment scores by exact (source, output) text: every HF row matched; HF z vs official wmt-z rho = 0.86-0.92 (2021-22), 0.97 (2020 controls). (`scripts/audit/audit_da_vs_official.py`, `results/audit_da_vs_official.csv`; mt-metrics-eval-v2 from data.statmt.org/wmt26/, extracted at ~/nobackup/archive/mtme/)
- **The official WMT21/22 into-English segment labels themselves carry ~no segment-level signal.** chrF vs official labels: 2021 cs -0.025, ja 0.036, is 0.036, ha 0.052; 2022 cs 0.10, ja 0.13, uk -0.007 (2020 controls 0.15-0.28). mt==ref outputs at the median under official labels (0.44-0.56; uk 0.49) vs 0.72-0.86 in 2020.
- **But system-level signal is intact.** Corpus chrF vs official system-level human z: 2021 cs 0.58, ja 0.83, is 0.86, ha 0.93; 2022 cs 0.96, ja 0.99, uk 0.90 (2020 controls 0.54-0.98). So raters weren't random; per-segment variation is noise while document/system means are informative -- consistent with WMT21's into-English SR+DC (segment rating with document context) protocol. (`scripts/audit/audit_da_system_level.py`, `results/audit_da_system_level.csv`)
- **Direction gap after excluding the dead-label years:** same-year cells 2017-2019 (labels pass mt==ref test): COMET-human gap +0.192, en->X wins 11/11; COMET~MetricX gap +0.014. 2020-2021 cells: +0.416. So a direction gap survives, roughly two-thirds of the headline size, but the metrics still agree with each other equally in both directions, so the residual remains confounded with the into-English crowd/reference-based vs out-of-English expert/source-based DA protocol.
- **Consequences:** any segment-level result on WMT21/22 X->en DA measures label quality, not metrics -- uk-en (all of Ukrainian), is-en, ha-en, and the 2021/2022 portions of cs-en and ja-en. Ukrainian "domain confound" (abstract) is wrong; Table 5's "complete metric failure in 2021" for cs-en is the same artifact.

## 2026-10-04 — Feedback from David Yarowsky (JHU) on the talk; vote vs. average check

Yarowsky's points: (1) the metric order in the heatmap needs a stated rule (he suggested release year, which might also show newer metrics correlate better); (2) use ISO 639-3 codes; (3) WMT languages aren't really low-resource; (4) ensembles (the paper already has a min-max ensemble of the 5 neural metrics, Table 3; Isaac forgot this in the Q&A); (5) **vote vs. average**: the decision table picks winners by per-language vote, so check whether averaging correlations first gives the same winner; (6) cells with 2-7 languages are too small for generalizable recommendations, so add a roll-up by direction and morphology plus significance and transfer; (7) state the hypothesis first.

Quick check of (5) from results/direction_separated_correlations.csv (pipeline output, all 9 non-GEMBA metrics; not re-derived):
- en->X fusional (n=7): the vote says CK23 (4/7) but the average says MetricX (.712 vs .696). **The two methods disagree.**
- en->X agglutinative (n=6): MetricX on both (4/6; .757 vs .753).
- X->en agglutinative (n=6): CK23 on both (5/6 over all metrics; .485 vs BLEURT .470).
- X->en fusional (n=7): CK23 on both (5/7; .311 vs MetricX .296).
- The top-2 average margins are .004-.016 everywhere, so they are probably not separable. The recommendation table should hedge en->X toward "MetricX or CK23".
TODO before the Budapest poster: compute properly via SSOT, with a bootstrap over languages on the top-2 margin.

## 2026-10-06 — MQM control for the follow-up paper

Script: scripts/audit/mqm_control.py (run_mqm_control.sh, m9; job 14000737). Reads official mt-metrics-eval-v2 files only. Outputs: results/mqm_control.csv and mqm_control_three_labels.csv.
Design: WMT20-22 have both expert MQM and WMT DA on the SAME (system, segment) set for zh-en (X->en) and en-de / en-ru (en->X). Pooled segment-level Spearman.

Results (mean over pairs; one X->en pair, zh-en, x3 years; five en->X pair-years):
- COMET vs MQM: en->X .433, X->en .531. **Under expert labels the direction gap REVERSES** (X->en is better).
- COMET vs DA: en->X .369, X->en .104. The AmanaMT-style gap appears only with DA labels.
- MQM vs DA agreement on the same segments: zh-en .155 (2020), -.018 (2021), .026 (2022); en->X .11-.41.
- WMT22 zh-en, three labels on the same 10,472 segments: COMET~MQM .533, COMET~source-based Appraise DA .458, COMET~crowd ref-based DA .023. **Same language and direction, different protocol: the protocol drives the effect.**
- Metric-metric agreement is flat (COMET~BLEURT en->X .791, X->en .858).

Lit check:
- Freitag et al. 2022 (WMT22 Metrics findings, App. B): "The segment level Kendal-like correlations of all metrics with Ref. DA scores are all very close to zero, and these numbers are completely meaningless. We strongly recommend against using Ref. DA scores to evaluate MT metrics." Ref. DA was used for all into-English directions (crowd).
- Freitag et al. 2021 (Experts, Errors, Context) covers WMT20 zh-en.
- Kocmi et al. 2021 (To Ship or Not to Ship) avoids crowd labels and cites the concern.
=> "Crowd into-English DA is bad at segment level" is ALREADY PUBLISHED. AmanaMT's direction headline rests partly on data WMT explicitly flagged.
Still possibly novel: (1) the known-bad slices silently produce a convincing typology finding via the RicardoRei HF dataset, which carries no flag; (2) the direction reversal under MQM, which needs more X->en MQM pairs (WMT23 he-en/zh-en, WMT24). Queued extraction of wmt23/wmt24 (job 14000739).
Caveats: the X->en MQM side is only zh-en, so direction is confounded with language; COMET-ref (2020) and COMET-22 were trained on WMT17-20 DA, and MetricX_MQM_2020 on MQM 2020.

### 2026-10-06 (cont.) — WMT23 added to the MQM control (job 14000851)
WMT23 used source-based DA+SQM in BOTH directions (no crowd), with MQM for en-de, zh-en and he-en (MQM only). WMT24 has no X->en pairs.
- COMET vs MQM, same-year: 2020 en-de .467 vs zh-en .568; 2021 en-de .307 / en-ru .403 vs zh-en .489; 2022 en-de .484 / en-ru .507 vs zh-en .535; **2023 en-de .578 vs zh-en .456 / he-en .482**.
  => The "reversal" claimed earlier today does NOT hold in 2023. Under expert labels there is no consistent direction effect (X->en ahead in 3 years, behind in 1). This is essentially en-de vs zh-en, so direction is confounded with language.
- 2023 source-based DA: MQM~DA agreement recovers for zh-en (.287, vs ~0 under crowd ref-based DA in 2021-22). COMET~DA en-de .429 vs zh-en .266: a gap of .16 remains under non-crowd DA, about half the crowd-era gap.
- Current best summary: most of the large DA direction gap comes from crowd reference-based DA in WMT21/22. With expert labels, direction has no consistent sign. Too few pairs (en-de, en-ru, zh-en, he-en) to claim a direction effect either way.

## 2026-10-06 (cont.) — Follow-up analyses (jobs 14000962, 14001006, 14001047)
Scripts in scripts/audit/: mtme_io.py (shared loader; the mqm_control refactor reproduces identical numbers), followup_analyses.py, da_retest_check.py, diagnostic_validation.py. Outputs: results/followup_*.csv.
- **A. Ranking flips** (all submitted metrics, 26-43 per slice; human-ref systems dropped first). Kendall tau between metric rankings under MQM and under DA: crowd zh-en .359 (2020), .016 (2021), -.226 (2022); source-based en->X .77-.90 (2020-22); WMT23 DA+SQM en-de .463, zh-en .739. Under crowd DA, surface metrics jump up: best surface rank 24->4 (2021 zh-en) and 11->1 (2022 zh-en; f200spBLEU ranks #1 under crowd DA).
- **B. Grouping**: item-grouped correlations reproduce the pattern (crowd zh-en COMET~DA item-grouped .007/.023 vs ~MQM .151/.298). System-level crowd DA is still informative (COMET .43-.67), with n_systems 8-15. WMT20 zh-en MQM system-level is negative (known oddity of that set).
- **C. Bootstrap** (1000x, resampling source segments), same-year en->X minus X->en gap. Under MQM: 2020 -.102 [-.142,-.065]; 2021 -.134 [-.180,-.089]; 2022 -.039 [-.072,-.005]; 2023 +.109 [.064,.154]. Under DA: +.073, +.334, +.382, +.163, all CIs >0. So under DA the gap is always positive and largest in the crowd years; under MQM the sign flips across years, and every CI excludes 0.
- **D. Ceiling**: DA "retest" pairs are copied scores in 2017 en->X, 2019 en->X and 2020 (84-96% exactly equal raw), so those are excluded. Independent years: crowd x->en single-rating reliability .127 (2021), .168 (2022) => ceiling .36/.41, yet COMET~DA = .008/.024, far below even that ceiling. MQM 3-rating reliability .74/.78 (WMT20), ceiling .86/.88. Caveat: duplicated outputs skew short and easy.
- **E. Diagnostic validation** (the follow-up's main contribution): D2 = (COMET~BLEURT) - (COMET~DA) predicts rho(MQM,DA): Spearman -.782, p=.008, n=10 slices. D1 = mt==ref percentile: .829, p=.042, n=6 (WMT22 en->X has no mt==ref cases; WMT23 is not in the HF data). Slices are not independent (shared years and systems). D2 also orders the non-crowd slices correctly (2021 en-de has the highest D2 and the lowest MQM~DA).
=> The follow-up looks viable as a separate paper: validated cheap diagnostic + ranking-flip consequence + bootstrapped sign-flipping direction gap.

## 2026-10-07 — Follow-up deferred; plan written
Isaac won't make the Oct 12 deadline with the follow-up. Plan and directions written to /home/it238/projects/amanamt-followup/PLAN.md. Since the follow-up won't exist when v2 posts, v2 summarizes the MQM control itself (one paragraph) instead of citing it.

## 2026-10-07 — arXiv v1 package frozen
archive/arxiv_v1/ holds arxiv_submission.zip, the published PDF, a fresh build from the zip, SHA256SUMS and README (made read-only). The build matches the proceedings PDF: 18 pages, identical text and digits apart from the publisher's header and page numbers. Upload it once the Anthology page is live.

## 2026-10-07 — arXiv plan revised
The uncorrected proceedings version will NOT be posted to arXiv (consistent with the Mapudungun decision). The first arXiv upload will be the corrected, retitled paper with a version note. archive/arxiv_v1/ is kept only as a frozen record of the published version (README now says DO NOT UPLOAD). Fixing the official record = ACL Anthology corrections process, if filed.

## 2026-10-09 — Audit loader validated against published WMT22 numbers
scripts/audit/reproduce_wmt22_tables.py (+ _variants.py), run on m9.
- Table 11 (Kendall tau vs MQM, flattened): **zh-en reproduced exactly** to 3 decimals for COMET-22, chrF, BLEU and metricx_xxl_MQM_2020, both with and without human translations (8/8). (The extracted PDF header had the column order swapped; fixed in the script.)
- en-de is about +.015 above published for every metric and system-set variant (a constant offset). Likely a data-version or system-set difference in the en-de MQM release; unresolved. It doesn't touch the zh-en evidence behind the corrections.
- Table 13 (DARR Kendall-like vs crowd Ref. DA, zh-en): not reproduced exactly. With metric ties ignored: chrF +.015 vs .025, BLEU +.022 vs .024, COMET-22 -.013 vs .002. WMT probably computes DARR from individual ratings rather than per-segment averages. Same conclusion either way (≈0); the published numbers themselves confirm crowd Ref. DA is ≈0 at segment level.
=> The audit's loading and correlation code is validated against an external source on the pair that carries the direction correction.

## 2026-10-17 — Data inventory: what AmanaMT omitted (Eric: "close the en->X isolating gap")
Script: scripts/audit/data_inventory.py -> results/audit_data_inventory_da.csv.
Cause: settings.toml excludes de/ru/zh from the DA tier ("already loaded as Tier 1a MQM"), and lang_from_pair collapses pairs to one language, so EVERY DA pair touching de/ru/zh was dropped.
- **en->zh (the "empty" en->X isolating cell) was available**: HF DA 2017-21 (109,681 rows); WMT19 DA (mtme); WMT22 source-based Appraise DA; WMT23 DA+SQM; WMT24 ESA; WMT25 ESA. **There is no en->zh MQM** anywhere in mt-metrics-eval v2 (wmt19-wmt25 checked). The other agent's "WMT22 en->zh MQM" claim is wrong: WMT22 en-zh is Appraise DA.
- DA omitted in total: 735,603 HF rows (en-de, en-ru, en-zh, de-en, ru-en, zh-en, plus fr-de).
- MQM omitted: the pipeline used HF RicardoRei MQM for 2020-22 only (en-de, en-ru, zh-en). Missing: WMT23 en-de and zh-en (the settings.toml comment "WMT20-23" is wrong); wmt21.tedtalks MQM (en-de, en-ru, zh-en; TED domain); wmt23.sent en-de; WMT24 en-de and ja-zh; WMT25 en-ko and ja-zh.
- Other protocols never used: WMT22 Appraise (9 pairs), WMT23 DA+SQM (7), WMT24 ESA (9), WMT25 ESA (16 pairs, 2 annotators each).
- Pooling: per-language (non-direction-separated) numbers pool opposite directions and X<->Y into one "lang" (e.g. cs = en-cs + cs-en + de-cs).
- WMT26 cESA (claimed by the other agent): not in the mtme tarball, unverified.

## 2026-10-17 — en->zh scoring queued (closing the en->X isolating gap)
scripts/score_en_zh.py + scripts/slurm/run_score_en_zh.sh (job 14271495, dwmatrix GPU; template: score_de_en.py). HF WMT DA en-zh 2017-21: COMET-22, CK23, MetricX-24, chrF++, BLEU-13a (pipeline-consistent) and BLEU-zh. Outputs: results/scores_en_zh.csv, en_zh_correlations.csv (pooled and per year). Protocol: source-based en->X DA, the same as the other en->X cells. Not yet in paper_stats.json.
**New issue found:** the pipeline's BLEU wrapper (src/mqmbench/metrics/bleu.py) uses sacrebleu's default 13a tokenizer for every target. That doesn't segment ja/zh/th/lo/my, so sentence-BLEU for **en-ja** (DA tier) and the th/lo/my Tier-2 targets is computed over unsegmented text. BLEU for those targets is near-meaningless, and the neural-vs-BLEU gap there is likely inflated. chrF (character-based) is unaffected. TODO: quantify for en-ja (rerun BLEU with tokenize="ja-mecab").
Terminology: call the 735,603 figure "rows" (rated HF items), not unique segments.

## 2026-10-17 — en-ja BLEU tokenization audit
scripts/audit/audit_bleu_tokenization_ja.py -> results/audit_bleu_tokenization_ja.csv (m9).
- The 13a recompute equals the checkpoint BLEU for 100% of the 24,434 en-ja rows, confirming the paper used untokenized BLEU for ja. Japanese hypotheses average 1.36 whitespace tokens.
- en-ja BLEU vs human: published **-0.000**; with FLORES-200 SPM tokenization (spBLEU) **0.238** (2020 .323, 2021 .233). chrF .273, COMET .543, MetricX .636, CK23 .611.
- Effect: the en->X agglutinative cell's gain of best neural metric over BLEU drops by ~.04 (my recompute .437 -> .397; paper macro TableFourEntoXAgglutin = .432). "Neural >> BLEU" is unchanged. Minor correction: one cell's BLEU baseline and the ja BLEU entries in the per-language tables.
- Also affected but exploratory: Tier-2 th/lo/my targets.
- Implementation note: sacrebleu.sentence_bleu(tokenize="flores200") reloads the SPM model on every call (OOM at 64G). Build sacrebleu.BLEU(..., effective_order=True) once; fixed in this script and in score_en_zh.py.

## 2026-10-17 — en->zh scored: the en->X isolating cell (job 14271495, 2h21m)
results/scores_en_zh.csv (109,681 rows), results/en_zh_correlations.csv. Source-based en->X WMT DA, 2017-21. MetricX wrapper returns 25-raw (higher = better).
- Pooled Spearman vs DA: COMET .510, CK23 .564, MetricX .534, chrF .293, BLEU-zh .307, BLEU-13a -.020 (untokenized; same flaw as en-ja).
- Per year, COMET: .606 (2017), .508, .563, .570, .404 (2021). CK23 is best every year except 2021, where MetricX is best.
- Table 2 context: en->X agglutinative .675, fusional .563; X->en isolating .462 (zh-en MQM + km-en DA, mixed protocols). The new en->X isolating cell (one language) = .510, so the isolating direction contrast is +.048. That's much smaller than the agglutinative (+.235) and fusional (+.271) gaps, but it is n = 1 language per side with protocols differing across the contrast. Report descriptively; no CI possible.
- Not yet in paper_stats.json. Adding the cell changes the eta^2 ANOVA inputs. If it goes into the corrected version, recompute through generate_paper_stats.py, not by hand.

## 2026-10-31 — Handoff written
Full state, decisions, paper edit list and open items: /home/it238/projects/amanamt-followup/HANDOFF.md. Corrected PLAN.md: WMT24 MQM+ESA overlap is en-es only, not en-de.

## 2026-11-05 — MetricX-24 EOS/padding bug (reported from the RL project; confirmed in code)
src/mqmbench/metrics/metricx.py:99-104 pads the batch (padding=True), THEN drops the last column ([:, :-1]). Official MetricX removes EOS per example BEFORE padding. Only the longest item per batch is correct (batch_size 32), so the rest keep </s> and lose a pad. Two-item test from the other project: 2.14 vs 0.85 raw. Scores depend on batch composition.
Affected: every AmanaMT MetricX-24 number (results/scores_metricx.csv, scores_de_en.csv and scores_en_zh.csv metricx columns, MetricX rankings/wins, decision procedure, Table 4/8, the en->zh .534).
NOT affected: the audit/MQM control (it used official WMT-submitted metric scores from mt-metrics-eval), and every COMET-based headline number.
Fix: tokenize unpadded, strip EOS per example, then pad (reference: ~/projects/reinforcement-learning/src/metricx_qe.py; keep the reference-based input format). Add a regression test (item alone == item batched with a long item). Also check the fast-tokenizer byte-fallback <unk> warning and the 1024-token truncation. Rescore needs a GPU.

## 2026-11-05 — Metric-wrapper audit (after the MetricX EOS bug)
- **GEMBA degenerate:** of 174,077 scored rows, 86.2% get the top quality value 1.0 (penalty 0). gemba.py returns penalty 0 for empty or unparseable output (failure = "perfect"). max_new_tokens=32 caps listed errors at about 1-2 per segment. The prompt is a custom format with major=5, minor=1 and no critical. This explains GEMBA ρ≈.035. Any GEMBA number (High tier, heatmap column) is a measurement of this wrapper, not of GEMBA-MQM.
- **BLEURT is English-only:** the settings use Elron/bleurt-large-512 (the 2020 BLEURT port, English uncased BERT vocab), not BLEURT-20. Japanese → partial [UNK], Cyrillic split into single characters, Turkish diacritics stripped. The paper (l.99) just says "BLEURT," with no caveat. BLEURT values for non-English targets (en->X) are out of scope for the model.
- COMET/xCOMET/Kiwi: wrapper fills missing scores with 0.0 silently, but no exact zeros are present, so there's no actual impact. BERTScore: mdeberta-v3-base, layer 10 known to bert_score; fine. chrF fine. BLEU: 13a tokenization issue (logged 10-17). MetricX: EOS bug (above); 267 rows at raw 25 (clamped worst) are plausible.

## 2026-11-05 — MetricX fix + full rescore submitted (job 15065631, dwmatrix A100)
- Fixed src/mqmbench/metrics/metricx.py: per-example EOS strip before padding (matches official MetricX). Added tests/test_metricx_batch_invariance.py (score alone == score batched with a longer item). The buggy version is saved at logs/metricx_buggy_reference.py for the before/after check in the job log.
- Backups (sha256'd): results/backup_pre_metricx_fix_2026-11-05/ (scores_metricx.csv, scores_de_en.csv, scores_en_zh.csv, en_zh_correlations.csv).
- Main rescore writes to results_metricx_fix/ via settings_metricx_fix.toml (only results_dir differs), recomputing chrF too. **Do not replace results/scores_metricx.csv until the new chrF matches results/scores_chrf.csv row by row** (positional alignment; checkpoint segment_ids are old-style and non-unique). Then rerun --analysis-only, generate_paper_stats.py, render_macros.py and assert_paper_invariants.py.
- de-en / en-zh: the metricx column is dropped and rescored in place by score_de_en.py / score_en_zh.py.

## 2026-11-07 — MetricX rescore resubmitted; parallel code checks launched
- Job 15065631 FAILED in 7s: pytest not installed in .venv, so nothing was rescored. Installed pytest; run_metricx_fix.sh now aborts if the regression test is skipped (fixture skips when the checkpoint is missing). Resubmitted as job 15131809.
- Four read-only code checks running in parallel; reports land in ~/projects/amanamt-followup/code_check/{wrappers,data,stats,ssot}/REPORT.md: (1) wrapper scores vs official mt-metrics-eval scores (COMET first); (2) data loading/filter/join/alignment; (3) independent recompute of headline stats + sign conventions; (4) SSOT/hardcoded-number/table-row provenance + citations + MetricX-dependent macro list.
- ssot check done (~/projects/amanamt-followup/code_check/ssot/REPORT.md). Pipeline/macros sound, but: eta^2_cell .618 is 1-dir-morph residual (generate_paper_stats.py:194); true between-cell eta^2 = .405 over 5 cells (verified independently). 13 hand-typed claims wrong/untraceable (domain/year composition L213/215/257, de-cs included L414, "5-15 MQM pairs", "22 additional pairs", kk pooled used as X->en max L357, best-metric candidate set 3 vs 7 vs 9 undisclosed, Kocmi quote misapplied). Repo scanner has major blind spots (skips \citet lines).
- stats check done (code_check/stats/REPORT.md). Arithmetic reproduces everywhere; row alignment correct. CONFIRMED by me: B1 en-ru WMT21 MQM is 100=perfect scale, WMT22 penalty scale, pooled + min-max => Russian "Simpson's paradox" is a label-scale artifact (pooled .157 -> .462 per-year z), and Medium>High reverses after B1+B2. B3 en-es ref offset in wmt_mqm.py maps seg g -> line g+1 (should be g-1): running job 15131809's es MetricX will be wrong (stored es scores used correct refs). Agent-reported, not yet re-verified by me: B2 he/es span rows split by <v> markers (es metrics inflated ~.1).
- data check done (code_check/data/REPORT.md). CONFIRMED by me: he/es span TSV target has <v>...</v> error markup and load_wmt_mqm_spans never strips it -> metrics scored text that marks where the human found errors (label leak). Agent: he COMET~human .713 published vs .518 with official COMET; es .586 -> .455; plus row splitting (one row per error) and QUOTE parsing drops 9.7% of he units. With all fixes he .482, es COMET .329. The Hebrew "COMET >> CK23" claim and High-tier means are now in doubt. Stats vs data agents DISAGREE on Medium vs High after fixes; resolve by recompute. Also: TED already in HF MQM 2021 (HANDOFF wrong); static direction labels mislabel 50% of DA rows in direction_analysis.csv/Ridge (Table 2/3 + eta unaffected).

## 2026-11-09 — MetricX rescore done; wrapper check (partial) clean for COMET family
- Job 15131809 COMPLETED (3h27m). Regression test passed; old vs new: alone 24.875 vs batched 23.375 (old) / 24.875 (new). results_metricx_fix/scores_chrf.csv matches results/scores_chrf.csv row by row on 98.5% of rows; the only mismatches are all 11,289 es rows (the en-es ref-offset bug: current code uses line g+1). Segment IDs differ only by new _N suffixes (content-aligned). MetricX changed on 93.5% of non-es rows (mean -0.41 on the 25-pt higher=better scale; still 257 distinct values = bf16). de-en/en-zh metricx rescored in place (old/new corr .976/.980). NOT yet swapped into results/scores_metricx.csv; es block must not be used (rebuild es anyway for the <v>-markup/row-split bugs).
- mt5 fast vs slow tokenizer: 4/2500 inputs differ, 3 contain <unk>; negligible; official MetricX uses the same fast tokenizer.
- Wrapper check agent died on a rate limit; its outputs are in code_check/wrappers/. Verified myself from sample_rerun_comet.parquet (2,100 non-es rows): stored COMET/Kiwi22/Kiwi23-XL/xCOMET vs pristine unbabel-comet fp32: Spearman >= .9997, mean abs diff <= .0014; human rho identical to 3 dp (COMET .397 vs .398). Core COMET results are safe. vs official mt-metrics-eval: WMT23 COMET/Kiwi rho .9997-.9999 (same single models); WMT22 COMET-22/COMETKiwi only ~.83-.87, most likely because the WMT22 official submissions were ensembles, not the released single checkpoints (not verified). BLEU exact for WMT22/23; chrF rho .99. BERTScore vs official .58-.63: different model (ours mdeberta), expected; the official-model rerun was never finished. en-zh BLEU vs official wmt20 rho .03: zh tokenization (known).

## 2026-11-09 — Label fixes implemented; he/es rescore + full regeneration queued
Code (backups of edited files in results/backup_pre_label_fix_2026-11-09/):
- wmt_mqm._normalize_per_lang: MQM quality_score = percentile rank within (lang, year) (was min-max within lang; en-ru 2021 100-pt scale vs 2022 penalty).
- load_wmt_mqm_spans: csv.QUOTE_NONE; strip </?v>; drop hotw-test, canary, refA. _SACREBLEU_OFFSETS en-es -1 -> +1 (verified vs mt-metrics-eval source alignment: he line g 820/820, es line g-1 622/623; external es ref file == mtme refA 999/999).
- New shared load_span_fallback_scores() used by pipeline.py and generate_paper_stats.py (both previously had their own ref-lookup code + offsets); asserts one row per (system, segment) and no empty refs. Result: he 9,840 rows (was 12,441), es 8,708 (was 11,289). vs official mtme MQM seg scores: Spearman he .9923 / es .9976, 100% matched (residual = official minor-punctuation weight 0.1; ours 1). 725 rows (he 496, es 229) have hyp == ref from real MT systems (ONLINE-B he 191): kept.
- pipeline --analysis-only: positional checkpoint fill now requires lang/tier row-by-row equality, and a length mismatch raises (was a silent partial fill).
- generate_paper_stats: EtaSqInteract (1 - dir - morph residual) replaced by EtaSqCell (between-cell one-way ANOVA) + EtaSqNCells/EtaSqNUnits; arxiv_submission/main.tex macro renamed (no prose change). assert_paper_invariants had replicated the residual formula; fixed.
- analyze_direction_separated: join key strips the loader's new _N suffix (restores the published join; 0-row join before); asserts a complete join.
- analyze_surface_similarity: same TSV fixes + refA dropped + n_raters was the number of error ROWS (penalty divided by own error count); now distinct raters. Paper uses only ChrFErrorFree he/de (refA chrF~1 was inflating it).
- validate_against_mt_metrics_eval: new ID format, shared offsets.
- compute_he_scores / compute_span_scores / compute_span_gemba: guarded (exit) as superseded.
- render_macros / generate_language_table / assert_paper_invariants: PAPER_DIR env (default latex). Regeneration targets arxiv_submission/; latex/ (published) untouched.
- tests/test_label_fixes.py (8 tests: within-year normalization, one row per unit, no markup/canary/refA, ref alignment vs mtme, official-MQM agreement > .98): pass.
Jobs: 15187848 (GPU) rescore he/es block with all metrics except GEMBA -> results/span_block_2026-11-09/. Then (afterok) regen job: snapshot -> splice_span_block.py (prefix kept, MetricX prefix from results_metricx_fix, he/es suffix replaced, GEMBA NaN) -> pipeline --analysis-only -> direction-separated -> surface/validation -> stats pass 1 -> abjad + Ridge -> stats pass 2 -> PAPER_DIR=arxiv_submission macros/table/plots -> invariants.
Not fixed (deferred, disclose): static direction labels in direction_analysis.csv/Ridge; human-ref systems in HF MQM/DA; Williams formula; degenerate win-fraction CIs; GEMBA wrapper.
- Follow-up fixes (before regen job 15187975 starts, so they land in the same run):
  - Win-fraction CIs: bootstrap_winner_fraction_ci now exact Clopper-Pearson (6/6 -> [.54, 1], 7/7 -> [.59, 1]; bootstrap gave degenerate [1, 1]). Paper text may still say "bootstrap".
  - Williams test (correlation.williams_test): full denominator 2K(n-1)/(n-3) + (r1h+r2h)^2/4 (1-r12)^3, on Spearman correlations (was sqrt(2K), Pearson).
  - Direction labels: correlation.MIXED_DIRECTION_LANGS (12 langs; single source, imported by generate_paper_stats and assert_paper_invariants) labelled "mixed" in per-language outputs (direction_analysis.csv etc.) instead of a fake static direction. DA composition (data audit): cs 70.9k en->X / 51.1k X->en / 13.8k pivot; tr 5.2k/30.2k; fi, et, ja, ... mixed. Ridge predictor now uses language-direction units (single-direction langs + mixed split from direction_separated_correlations.csv), LOLO folds by language; summary.json gains n_units; new macro RidgeNUnits. Dry run on pre-fix data: 9/38 units (published 5/26); still negative.
  - Human-reference systems in HF MQM: checked; none is scored against itself (Human-A/B/P, ref-A..D, refB are other human translations; en-de 2021 ref-B equals the reference on 32% of rows). Kept as published; disclose.
  - GEMBA: not rescored; recommend drop/relabel in the corrected text.

## 2026-11-09 (later): regen after label fixes — DONE
- Jobs: span rescore 15187848 OK (20 min). Regen 15187975 died at step 5 (generate_paper_stats read predictor `n_units` before the predictor was rebuilt; now guarded). Resumed from step 5 as 15190223 (scripts/slurm/run_regen_after_label_fix_resume5.sh): OK.
- 265 of 643 macros changed. Pre-fix outputs: results/backup_pre_label_fix_2026-11-09/analysis_outputs.tgz. Diff list: /tmp/macro_diff.txt (regenerate by diffing that tgz's paper_stats.json).
- Per-language COMET MQM rho, old→new: ru .157→.455, he .713→.484, es .586→.326, de .425→.427, zh .447→.489. The he/es inflation is most likely the <v> markup leak (tags only on error spans, so metrics "see" the labels).
- Claims that flip:
  - "Spanish strongest MQM" → now weakest.
  - Medium>High: High > Medium for every neural metric (COMET .464 vs .396, MetricX .556 vs .457); only BLEU/chrF/BERTScore still marginally Med>High.
  - Russian "suppression" (year-stratification) is gone: RuDelta .285 → −.013. The finding was the scale-mix bug; the Czech masking example still holds.
  - "MetricX wins all but two (ru, he)": MetricX now beats COMET everywhere.
  - CK23 X→en: agglutinative 6/6 → 5/6, fusional 6/9 → 4/9, so "CK23 wins consistently" is weaker.
  - LOO 19/26 → 17/26 (73→65%). Pivot MetricX wins 4/5 → 5/5.
- Hebrew abjad: Cohen's d (COMET) 1.98 → 1.10, z .058 → .351. Weaker but still a large effect.
- η² (COMET, 33 units / 5 cells): dir .309→.381, morph .073→.094, cell .517 (new between-cell definition). Direction > morphology survives. DiD .036→.065.
- Ridge: CK .558→.545, CK23 .469→.502, rec acc 5/26 → 6/38 (38 units = mixed langs split by direction).
- Invariants: 5 failures, all hand-typed literals in assert_paper_invariants.py / main.tex (DiD .036, Ridge .558/.469, 5/26, the Table direction_full bold set + caption "all but two (ru, he)").

## 2026-11-10: Eric's audit triage, v2 code fixes, v2 text composed
- Eric Ringger's code audit (notes/amana-mt-audit.md) was of the lab mirror at 3239cec (May 8). Triage against the current tree: notes/amana-mt-audit-triage.md.
- Code fixes:
  - New src/mqmbench/analysis/metric_scope.py: GEMBA excluded (99.6% of segments score 1.0); BLEURT English-target only. Applied in pipeline.py, analyze_direction_separated.py and generate_paper_stats.py.
  - correlation.py: the bootstrap resamples source sentences (`groups=`); correlate_metric_vs_human drops NaN pairs jointly; reference_quality_effect no longer uses fillna(0).
  - tests/test_v2_stats.py: Williams vs a verbatim copy of mt-metrics-eval WilliamsTest (commit 68a481a); size under the null; grouped bootstrap; scope. 24 tests pass (2 MetricX GPU tests deselected on the login node).
- Regen job 15224383 (scripts/slurm/run_regen_v2_fixes.sh): only BLEURT and NumMetrics (10 -> 9) changed among point estimates. CIs widened: median 1.19x, max 2.7x (MQM languages). Pre-fix snapshot: results/backup_pre_v2fixes_2026-11-10/.
- MQM control: reran scripts/audit/followup_analyses.py (job 15224394) so followup_bootstrap_ci.csv has the gap rows. generate_paper_stats.py now emits MqmCtrl* macros and checks that the points match mqm_control.csv. The control reads official mtme files only, so it is unaffected by the label bugs.
  - MQM gaps (en->X minus X->en, COMET): -.102, -.134, -.039, +.109.
  - DA gaps: +.073, +.334, +.382, +.163. All CIs exclude 0.
- New findings during the rewrite:
  - The mixed-model morphology term is now significant (p=.037); it was published as non-significant.
  - Year-strat en->X fusional: .567 -> .565 (no longer "a small increase").
  - MetricX-24 has the highest mean in every tier and every direction (among single metrics).
- assert_paper_invariants.py:
  - DiD, Ridge and RecAcc are now compared to the macros.
  - Table direction_full bolds are now parsed from main.tex.
  - Section M checks the metric scope.
  - Result: 66 checks, all pass.
- arxiv_submission/main.tex rewritten as v2: new title, version note, abstract, MQM-control subsection (sec:mqm_control), label-quality discussion (sec:label_quality), and revised Limitations. Pre-rewrite copy: results/backup_pre_v2fixes_2026-11-10/main.tex.pre_v2text.
- Bib: freitag2022results and graham2014testing were fetched from the ACL Anthology.
- Fig 1 in-image title reworded (make_presentation_plots.py:242).
- Compiles to 17 pages, with no errors and no undefined citations or references.
- Strict number scan reviewed; exceptions in notes/v2_scan_exceptions.md.
- Open:
  - Isaac's review of the text.
  - Verify that WMT21 is-en/ha-en DA is crowd reference-based (claimed in the Ukrainian paragraph and the Table 8 caption).
  - Acknowledgments: maybe thank Eric for the audit.
  - Independent recompute.
  - reportkit claims/lint.
  - Merge to main before linking the repo.

## 2026-11-11: recompute findings fixed; v2 text approved
- Isaac approved the v2 text as diffed, with two changes: never write "CK23" (now "CometKiwi-23" everywhere, figures included; reportkit bans it), and Eric Ringger as second author (acks sentence thanking him removed). v2 goes to the ACL Anthology as a revision, not arXiv.
- Approved text backed up: results/backup_pre_v2fixes_2026-11-10/main.tex.approved_2026-11-11.
- Independent recompute (fresh agent; scripts in ~/projects/amanamt-followup/code_check/recompute_v2/): 74/75 checks within .005 and no headline flips. Its findings and what was done about each:
  1. TotalSegments was typed (730,748, counting the old span block). Now computed from correlations.csv = 725,566, and asserted equal to the scores_comet.csv row count.
  2. The he/es span labels used critical=25 and punctuation=1. converter.wmt_mqm_weight now applies the official weights (non-translation 25, critical/major 5, minor punctuation 0.1, minor 1), via scheme="wmt" for the span files only; Tier 2 is unchanged. test_agrees_with_official_mqm now requires exact segment-score agreement (>99.9%): it passes for he and es.
  3. The version note wrongly said the published en-es references were offset. The offset came from commit 7a65176, after publication. Removed from the abstract, version note and Hebrew paragraph.
  4. "Identical segment sets": the WMT23 MQM gap includes he-en (no DA). Reworded.
  5. Human-reference systems in the WMT20-22 control sets: dropping them moves the WMT20 MQM gap -.102 -> -.058, signs unchanged (recompute). Disclosed qualitatively in sec:mqm_control.
  6. High > Medium is thin under per-language averaging (about .005). Hedged in the text.
- Regen job 15262250 (scripts/slurm/run_regen_wmt_weights.sh; snapshot results/backup_pre_wmtweights_2026-11-11/).
- ~/projects/amanamt-followup/PLAN.md: new section "Attempted in v1, dropped or weakened in v2", covering the claims dropped, the methods removed or restricted, and the label-assembly bug list.
- reportkit (reportkit.toml, tools/reportkit_claims.py): claims 28/28, lint 0. All claims fire on the published text (falsify check). The PDF half is skipped because the cluster has no pdftotext.
- 2026-11-11 (later): AM_regen 15262250 COMPLETED (2h20m, all invariants pass).
  - 51 macros changed, all from the he/es reweighting. The largest is LangBERTScoreHE .335 -> .329 (-.0057, accepted by Isaac); the rest are <= .004. TotalSegments = 725,566.
  - Rebuilt main.pdf (17 pp) and diff.pdf (22 pp). Checks: invariants 66/66, reportkit claims 28/28, lint 0.
  - Verified from WMT21 findings (Akhbardeh et al. 2021): into-English, including ha-en and is-en, used crowd reference-based monolingual DA (p. 11; Table 6, p. 14), so the Ukrainian paragraph and the Table 8 caption stand.
  - Committed ccd34fe on publishability-upgrades (73 files; Eric's audit and triage left untracked; results_metricx_fix/ and the diff build gitignored). Fast-forwarded local main to it. NOT pushed.
