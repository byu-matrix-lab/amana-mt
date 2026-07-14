# Competitive Landscape & Reviewability Assessment: "MT Metric Reliability Across Resource Levels, Morphological Complexity, and Domain" (EMNLP 2026 Findings)

## TL;DR

- **The paper has a viable Findings-tier story IF you reframe the headline.** The morphology axis is at meaningful risk only from one summarization paper (Mondshine, Paz-Argaman & Tsarfaty, "Beyond N-Grams," ACL 2025 Long Papers Vol. 1, pp. 19019–19035, Vienna, Austria; arXiv 2507.08342) — no MT paper makes the morphology-as-reliability-driver claim, and Mondshine's neural-metric trend is *reversed* from yours, which is exploitable rather than fatal. The direction-asymmetry claim appears genuinely unclaimed in the MT-metric literature.
- **The domain-confounds-resource-level finding is the strongest novel contribution and should be the title.** Zouhar et al. (ACL 2024 short, biomedical) establishes that fine-tuned metrics break under domain shift, but no one has shown that what the field reads as "Ukrainian is low-resource and metrics fail" is actually a domain confound — and the WMT24 General MT findings paper explicitly states that Czech→Ukrainian "uses different domains" from the rest of WMT24, which is the smoking gun you can cite.
- **One factual claim in the paper needs immediate correction**: the WMT24 Czech→Ukrainian conversational data is from the Charles Translator mobile app (Personal/Voice/Official/Educational domains), **not Telegram**. If your Telegram corpus is a separate Tier-2 source, that needs to be made explicit; if you have been calling WMT24 Cs→Uk "Telegram," that is wrong and reviewers will catch it.

## Key Findings

### 1. The three most directly competing papers

**(a) Freitag et al., "Are LLMs Breaking MT Metrics? Results of the WMT24 Metrics Shared Task"** (Proceedings of the Ninth Conference on Machine Translation, ACL Anthology 2024.wmt-1.2, pp. 47–81, Miami, November 2024). This is the dominant benchmark paper. It evaluates metrics on three MQM language pairs (en→de, en→es, ja→zh) plus ESA across additional pairs, in four domains (news, literary, speech, social). Crucially, it covers only three MQM pairs while your paper covers 32 languages × 3 annotation tiers — you have a clear scale advantage on language coverage, but they have the reference annotation protocol that reviewers consider canonical. **Reviewer risk**: they will ask why your Tier-1a doesn't include the WMT24 MQM data itself (it should, or you must justify omission).

**(b) Zouhar, Ding, Currey, Badeka, Wang & Thompson, "Fine-Tuned Machine Translation Metrics Struggle in Unseen Domains"** (Proceedings of the 62nd ACL, Vol. 2 Short Papers, pp. 488–500, Bangkok, August 2024; arXiv 2402.18747). This is the single most important paper for your domain claim. They release "roughly 25k segment-level annotations spanning 11 translation directions" (Pt→En, En↔De, En↔Es, En↔Ru, En↔Fr, Zh↔En) and 21 translation systems in the biomedical domain, and demonstrate that fine-tuned metrics (COMET, BLEURT, UNITE) drop substantially relative to surface-form (BLEU, chrF) and non-fine-tuned pre-trained metrics (BERTScore, PRISM) under domain shift. **What they do not do**: argue that the apparent low-resource problem in any specific language is actually a domain confound. That reinterpretation is your contribution, but it must be framed as building on Zouhar 2024, not as the first observation that domain matters.

**(c) Mondshine, Paz-Argaman & Tsarfaty, "Beyond N-Grams: Rethinking Evaluation Metrics and Strategies for Multilingual Abstractive Summarization"** (ACL 2025 Long Papers Vol. 1, pp. 19019–19035, Vienna; arXiv 2507.08342). This is the highest novelty risk for the morphology axis. They evaluate metrics across 8 languages split into four typological families — isolating (ZH, YOR), agglutinative (JA, TR), low-fusional (ES, UK), high-fusional (AR, HE) — and report that "for fusional languages, n-gram-based metrics demonstrate a lower correlation with human assessments, compared to isolating and agglutinative languages." **Three reasons this does not kill your novelty**: (i) the task is summarization, not MT (they explicitly note theirs is "the first work to suggest COMET for evaluating a non-MT task"); (ii) the direction effect is absent (summarization is monolingual); (iii) crucially, their neural-metric finding is the *opposite* of yours — COMET correlates *better* with humans for fusional languages in their results (coherence Pearson ≈0.35 for high-fusional vs 0.07 for isolating), whereas your paper claims surface metrics hurt most for agglutinative languages, which is consistent with the n-gram half of their result. **You must cite Mondshine et al. and explicitly contrast the MT vs. summarization regime.**

### 2. Secondary competing / overlapping papers

- **Yari, Kulkarni, Khan & Koto, "Revisiting Metric Reliability for Fine-grained Evaluation of MT and Summarization in Indian Languages"** (arXiv 2510.07061, October 2025). Introduces ITEM, a benchmark of 26 metrics across 6 Indian languages (Hindi, Bengali, Marathi, Gujarati, Tamil, Telugu). Reports the anomaly verbatim: "Notably, Hindi—a high-resource language—is evaluated less reliably than lower-resource languages like Tamil and Telugu, revealing an unexpected anomaly in LLM-based assessments that contrasts with previous evidence of superior performance in high-resource settings." This is essentially a smaller-scale, single-region version of your medium > high-resource anomaly finding, and you must cite it and position your work as the cross-typology generalization.
- **Wang et al., AfriCOMET (NAACL 2024) and Li et al., SSA-COMET (arXiv 2506.04557, 2025)**. Both frame the problem as low-resource / encoder coverage, not morphology. They are useful citations to motivate why "low-resource" has been the dominant frame — supporting your novelty.
- **Kocmi et al., "Findings of the WMT24 General MT Shared Task: The LLM Era is Here but MT is Not Solved Yet"** (ACL Anthology 2024.wmt-1.1, pp. 1–46). Confirms the Cs→Uk-different-domains fact you need: "Czech-Ukrainian data was collected separately, comprising news data and four other separate domains" — Educational, Personal, Official, Voice (Charles Translator mobile app). This is the citation that makes your Ukrainian-is-domain argument quotable.
- **Falcão, Borg, Aranberri & Abela, "COMET for Low-Resource MT Evaluation: A Case Study of English-Maltese and Spanish-Basque"** (LREC-COLING 2024). Small-scale single-language-pair version of the resource-level question — useful to cite as motivation.
- **Sai et al., "IndicMT Eval"** (arXiv 2212.10180; 7,000 MQM annotations across 5 Indian languages and 7 MT systems) — your Tier-1a precedent for "small but expert" MQM at scale.
- **Bugliarello, Mielke, Anastasopoulos, Cotterell & Okazaki, "It's Easier to Translate out of English than into it: Measuring Neural Translation Difficulty by Cross-Mutual Information"** (arXiv 2005.02354). XMI is about translation *difficulty*, not metric reliability, but it is the obvious citation for the direction-asymmetry literature.
- **Kocmi, Federmann, Grundkiewicz, Junczys-Dowmunt, Matsushita & Menezes, "To Ship or Not to Ship: An Extensive Evaluation of Automatic Metrics for MT"** (EACL 2021) and **Kocmi & Federmann 2023 (GEMBA-MQM)** — the pairwise-accuracy meta-evaluation precedents.
- **Deutsch, Foster & Freitag, "Ties Matter: Meta-Evaluating Modern Metrics with Pairwise Accuracy and Tie Calibration"** (arXiv 2305.14324) — methodological precedent for your meta-evaluation; reviewers will ask whether you used tie-calibrated accuracy in addition to Williams.
- **MetricX-24 (Juraska, Deutsch, Finkelstein & Freitag, WMT 2024.wmt-1.35, pp. 492–504)** — currently the top-performing MT metric, which you should add to your ensemble.

### 3. Reviewer expectations for an EMNLP Findings meta-evaluation paper

Based on the WMT24 metrics task and recent Findings/main-conference acceptances:

- **Scale**: The EMNLP 2020 committee blog confirms verbatim that "accepted to Findings equates to 15.5% of the reviewed papers, giving an aggregate acceptance rate for EMNLP and Findings of 37.9%." Recent Findings-accepted meta-evaluation papers (Mondshine 2025 went to ACL main; ITEM is on arXiv; Zouhar 2024 took ACL short) typically cover **8–13 languages with expert MQM, or 20+ languages with DA-style annotation**. Your 32 languages × 3 tiers is *above* the typical Findings bar — this is a strength.
- **Metrics**: 10 metrics including BLEU, ChrF, BLEURT, BERTScore, COMET, xCOMET, two CometKiwi variants, GEMBA-MQM, plus an ensemble is **at or above** the WMT24 baseline set. The conspicuous absence is MetricX-24 (Google's WMT24 hybrid winner) and arguably MetaMetrics-MT — adding at least MetricX-24 is essentially mandatory.
- **Annotation type**: Three-tier design is *unusually thorough* — most papers use one of MQM, DA, or ESA. Your Tier 2 synthetic GEMBA-MQM via Llama-3.1-8B will be the most contested choice and must be validated against either a small human-MQM subset for 1–2 of the very-low-resource languages, or against GPT-4 GEMBA-MQM, or against ESA. The MQM-APE paper (Lu et al., arXiv 2409.14335) reports that GEMBA-MQM error annotations align poorly with human annotators — "Precision for span and 'major error' overlap is low (e.g., span precision 9.0%, major error precision 4.9%)" — and reviewers will demand validation.
- **Statistics**: Williams test plus pairwise accuracy is appropriate; consider adding tie-calibrated accuracy (Deutsch et al. 2023) and soft pairwise accuracy (Thompson et al., arXiv 2409.09598). The WMT24 metrics task uses six different correlation tasks weighted-averaged — at minimum acknowledge this.

### 4. Novelty risk assessment by claim

| Claim | Most threatening prior | Risk level | Mitigation |
|---|---|---|---|
| COMET dominates across tiers, 9/12 languages, Williams p≈0 | Freitag 2024 (WMT24), Kocmi 2021, AfriCOMET | **Low novelty but expected baseline finding** | Frame as confirmation, not contribution |
| Medium > high resource anomaly explained by multi-year heterogeneity | Yari et al. ITEM 2025 (Hindi anomaly) | **Medium** | Cite ITEM; position as scaled cross-region generalization |
| Ukrainian collapse is domain, not language | Zouhar 2024 (domain shift); Kocmi 2024 (Cs-Uk different domains) | **Low — strongest contribution** | Cite both; emphasize that no one has done the domain-vs-resource disentanglement |
| Surface metrics hurt most for agglutinative languages | Mondshine 2025 (summarization); long folklore | **Medium-high** | Cite Mondshine; emphasize MT-specific and direction-aware nature |
| Direction asymmetry (X→en vs en→X) drives reliability | None systematic; Bugliarello 2020 (difficulty only) | **Low — genuinely novel** | Make this a headline; ensure significance tests are direction-stratified |
| Khmer high (ρ=0.476), Russian anomaly (ρ=0.157) | None directly | **Low** | Investigate Russian data quality as a contribution rather than caveat |
| Synthetic GEMBA-MQM Tier 2 for very-low-resource | Sai et al. 2024 (en-hi GEMBA-MQM); MQM-APE 2024 (alignment concerns) | **High methodological risk** | Validate Tier 2 against at least one small human-annotated sample |

## Details

### What the morphology claim actually faces

Mondshine et al. (ACL 2025) is the closest match in the entire literature, and their findings are nuanced in a way that helps you. They report Pearson correlations between automatic metrics and human ratings on summarization in 8 languages from 4 typological families. For n-gram metrics (ROUGE, CHRF, BLEU), correlations with the "coherence" dimension drop sharply for high-fusional languages (e.g., CHRF coherence: 0.02 for isolating, 0.09 for agglutinative, 0.16 for low-fusional, **−0.46 for high-fusional**). For COMET — which they repurpose for summarization — the pattern *reverses*: COMET coherence Pearson goes from 0.07 (isolating) to 0.23 (agglutinative) to 0.23 (low-fusional) to 0.35 (high-fusional). They also show BLEU-Lemmatized on high-fusional completeness rises from −0.10 to +0.40 after lemmatization.

Your claim that surface metrics hurt most for agglutinative languages is consistent with their n-gram half but extends a different typological cut (you split agglutinative from fusional rather than lumping them together as "morphologically rich"). The reviewer-level move is: cite Mondshine 2025 explicitly, note that they study summarization with monolingual evaluation, and argue that the MT setting introduces translation direction as a confounded factor that they cannot capture. Your direction × morphology interaction is the genuinely new finding.

### What the Ukrainian/domain claim actually faces

The WMT24 General MT findings paper (Kocmi et al., aclanthology.org/2024.wmt-1.1.pdf) confirms verbatim that "Czech-Ukrainian data was collected separately, comprising news data and four other separate domains" and that the conversational domains are sourced from the Charles Translator mobile app, with categories Educational, Personal, Official, and Voice (the latter ASR-transcribed). Table 2 of that paper notes that "Czech→Ukrainian is not included because of different domains and source data" when comparing GEMBA scores across the rest of WMT24.

**This is the single most quotable fact you have.** It means the Cs→Uk numbers in WMT24 are not directly comparable to en→X numbers from the same shared task — they come from a fundamentally different domain distribution. Anyone who has read WMT24 carefully knows this, but no published paper has used it to argue that the apparent Ukrainian-metrics-collapse story in the broader literature is a domain artefact.

**However, two corrections are needed to your draft framing**: (i) the WMT24 Cs→Uk conversational data is from Charles Translator mobile app, not Telegram. If you are using a separate Telegram corpus as your own dataset, make that source explicit in the methodology. If you have been describing WMT24 Cs→Uk as "Telegram," that is incorrect and reviewers will catch it instantly. (ii) Zouhar et al. 2024 (the biomedical-domain robustness paper) is the canonical citation for "fine-tuned metrics break under domain shift" — your contribution is the *resource-level disentanglement*, not the domain-shift effect itself.

### What the direction asymmetry claim actually faces

I found no MT-metric paper that makes a systematic claim that translation direction drives reliability differently. The closest is Bugliarello et al. 2020 (XMI), which is about translation *difficulty*, not metric correlation with human judgments. The COMET paper (Rei et al. 2020) reports separate Kendall's tau tables for "English as source" vs "English as target" but does not theorize the asymmetry as a metric-reliability axis. WMT findings papers typically aggregate across directions. **This appears to be a genuinely open claim** and should be a headline.

### What the medium > high resource anomaly faces

Yari, Kulkarni, Khan & Koto (arXiv 2510.07061, October 2025) reports the anomaly verbatim: "Notably, Hindi—a high-resource language—is evaluated less reliably than lower-resource languages like Tamil and Telugu, revealing an unexpected anomaly in LLM-based assessments that contrasts with previous evidence of superior performance in high-resource settings." This is essentially the same anomaly you observe but constrained to Indian languages and attributed to LLM-based metrics specifically. Your "multi-year heterogeneity" explanation (i.e., that high-resource MQM pools span multiple WMT years with shifting MT system quality) is a *mechanistic* explanation Yari et al. do not provide. Cite their observation; claim the mechanism as your contribution.

### What the Tier 2 design faces

Synthetic GEMBA-MQM via Llama-3.1-8B for 7 very-low-resource languages is the most reviewer-flammable element. Three known issues from the literature:

- **Span alignment**: Lu et al. (MQM-APE, arXiv 2409.14335) report verbatim that "Precision for span and 'major error' overlap is low (e.g., span precision 9.0%, major error precision 4.9%)" for GEMBA-MQM against human annotators.
- **Low-resource performance of GEMBA-MQM**: Kocmi & Federmann (2023, the original GEMBA-MQM paper) explicitly flag as a limitation: "High-Resource Languages Only: As WMT evaluations primarily focus on high-resource languages..." Llama-3.1-8B is a much smaller backbone than GPT-4, exacerbating this.
- **Synthetic data validation precedent**: Sai et al. 2024 ("How Good is Zero-Shot MT Evaluation for Low Resource Indian Languages?") ran GEMBA-MQM on Indian languages with mixed results; you should cite them as the methodological precedent.

**Mitigation**: validate Tier 2 against a small human-annotated sample for at least one of the 7 very-low-resource languages, ideally via ESA (Kocmi, Zouhar et al. WMT 2024) which is cheaper than MQM but expert-quality enough.

### The metric set

Your 10 metrics cover all the WMT24 baseline families except MetricX-24 (Juraska et al. 2024), which was the top performer on the WMT24 main meta-evaluation. Reviewers will explicitly ask why MetricX-24 is missing — adding it is essentially mandatory. MetaMetrics-MT (arXiv 2411.00390) is the second most likely "why didn't you include..." question; cite it as future work if you cannot run it.

## Recommendations

### Stage 1 — before submission (mandatory)

1. **Reframe the title and abstract to lead with the domain-confounds-resource-level finding**, not the morphology finding. Something like "What Looks Like a Low-Resource Problem Is Often a Domain Problem: A 32-Language Meta-Evaluation of MT Metric Reliability." The morphology and direction findings then become secondary contributions.
2. **Add MetricX-24 to the metric set** (Juraska, Deutsch, Finkelstein & Freitag, WMT 2024.wmt-1.35). Skipping the WMT24 winner is the single most predictable reviewer complaint.
3. **Correct the Telegram claim**. Confirm the actual source of your Ukrainian conversational data. If it is WMT24 Cs→Uk, the source is Charles Translator mobile app, not Telegram. If it is your own Telegram corpus, label it as such and explain how it was constructed and annotated.
4. **Validate Tier 2 synthetic GEMBA-MQM against human annotation** for at least one of the 7 very-low-resource languages. Even 200 ESA-annotated segments per language would suffice and would defang the predictable "synthetic ground truth is not ground truth" objection.
5. **Add tie-calibrated pairwise accuracy** (Deutsch, Foster & Freitag, "Ties Matter," arXiv 2305.14324) alongside Williams test. Williams alone will read as dated to a WMT-savvy reviewer.

### Stage 2 — strengthen the morphology and direction arguments (high priority)

6. **Explicitly contrast with Mondshine et al. (ACL 2025 Long Papers Vol. 1, pp. 19019–19035; arXiv 2507.08342)** in the related work section. State that (i) they study summarization, (ii) their neural-metric trend reverses your surface-metric trend, and (iii) direction is absent from their setting. This converts a novelty threat into a citation.
7. **Run a 2×3 interaction analysis: direction × morphology**, with effect sizes (eta-squared or partial eta-squared) and bootstrapped confidence intervals. The interaction is the novel claim; the marginal effects are well-known.
8. **Stratify all primary results by translation direction.** This is the headline novelty — if it is not visible in your main tables, reviewers will not see it.

### Stage 3 — strengthen the domain claim (high priority)

9. **Quote the WMT24 Cs→Uk "different domains" statement directly** from Kocmi et al. 2024 in the introduction, then run an explicit decomposition: hold the language constant (Ukrainian) and vary domain, vs. hold the domain constant and vary the language. If both are not in the paper, the "domain not resource" claim is conjectural rather than demonstrated.
10. **Cite Zouhar et al. (ACL 2024 short, biomedical) as the immediate precedent.** Your framing should be: Zouhar showed fine-tuned metrics break under domain shift in a controlled biomedical setting; we show that this same effect, when uncontrolled, has been *misread as a low-resource problem* in the broader literature.

### Stage 4 — opportunistic additions

11. **Investigate the Russian ρ=0.157 anomaly as a positive contribution**, not a caveat. The literature documents WMT Russian reference-translation quality concerns (e.g., Zouhar & Bojar 2024 on reference quality); if you can show the anomaly resolves with reference replacement or quality filtering, this is a publishable finding rather than a defensive footnote.
12. **Investigate Khmer's surprisingly high ρ=0.476** — Khmer is isolating with a non-Latin script and very low resource by any standard count. If the explanation is "isolating morphology is easier for metrics even at very low resource," that becomes additional evidence for the morphology axis being primary over the resource axis.

### Stage 5 — decision benchmarks

If you cannot:
- Add MetricX-24, **drop to a Findings short or workshop submission** (the metric coverage will be flagged as incomplete).
- Validate Tier 2 against any human annotation, **drop the synthetic-tier claim from the main story** and present it as exploratory/qualitative — keeping it as a "key finding" without validation is the single biggest rejection risk.
- Disentangle domain from resource level empirically for Ukrainian, **soften the "is actually a domain problem" claim to "may be confounded by domain"** — the strong form requires the disentanglement analysis.

## Caveats

- **The user's description of WMT24 Cs→Uk as "Telegram"** appears to be a factual error or an unstated separate corpus. The WMT24 conversational Czech-Ukrainian data comes from the Charles Translator mobile app (Personal, Voice, Official, Educational domains). This must be resolved before submission.
- **Mondshine et al. 2025 is the highest-cited threat to morphology novelty.** Their summarization frame is the load-bearing wall in your novelty argument — if a reviewer reads it as "morphology effect on metrics is already documented," your morphology contribution shrinks to "we extended it to MT." That is still publishable but is a Findings-tier contribution at best.
- **ITEM (Yari et al., arXiv October 2025)** is recent enough that not all reviewers will have seen it, but at least one will. Cite it.
- **GEMBA-MQM is known to be a poor proxy for human MQM annotations** at the span level (Lu et al., MQM-APE, arXiv 2409.14335: span precision 9.0%, major-error precision 4.9%). Llama-3.1-8B will be worse than GPT-4 on this. Your Tier 2 design needs validation that does not rely on GEMBA-MQM as ground truth.
- **EMNLP 2026 will use ACL Rolling Review** (per the official 2026.emnlp.org call) — your timing depends on ARR cycle dates, not the EMNLP-only schedule. Plan accordingly.
- **The medium > high resource anomaly with "multi-year heterogeneity" as the explanation** is a hypothesis your paper must demonstrate, not just assert. The fix is a sub-analysis holding WMT year constant.
- **Significance-test caveat**: "Williams p≈0" is suspiciously clean. Report exact p-values or report the test statistic; reviewers reading "p=0.000" will assume an underflow or a sloppy report.
- All quoted findings from Yari et al. (ITEM, October 2025), Mondshine et al. (ACL 2025), and the SSA-COMET paper (arXiv June 2025) refer to recent papers, some of which are on arXiv only — confirm publication status before citing in camera-ready.