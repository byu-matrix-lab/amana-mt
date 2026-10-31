# AmanaMT presentation Q&A

Use the first sentence of each answer first. Add the remaining detail only if the questioner wants it.

## What do English-to-X and X-to-English mean?

English-to-X means English is the source language, while X-to-English means English is the target. In the original DA benchmark, metric-human agreement is stronger in the English-to-X direction, but follow-up controls show that much of this gap is protocol-sensitive.

## Why might translation direction matter?

A large part looks like annotation protocol. WMT's into-English labels in 2021 and 2022 came from crowd workers comparing translations against the reference. On the same Chinese-to-English segments, COMET correlates .53 with expert MQM but .02 with crowd Direct Assessment. Asymmetric metric-training coverage, reference quality, and source-versus-target complexity remain plausible secondary mechanisms that require controlled tests.

## Could similar data produce the opposite conclusion?

Yes. Under expert MQM on WMT 2020 through 2023, the direction gap changes sign across years, so I treat the original result as protocol-sensitive. Chinese-to-English is ahead in 2020 through 2022 but behind in 2023. The available expert comparison contains too few language pairs to support a universal direction effect.

## Why is Spanish labeled medium-resource?

The tier describes the evaluation dataset, not Spanish as a language. Spanish comes from one recent WMT year with a different system and annotation cohort, while the high tier contains heterogeneous multi-year MQM pools. Moving Spanish to high would blur that design difference rather than add information.

## Why are COMET and COMET-Kiwi-23 so closely correlated?

Their agreement shows that a reference-free metric can often recover the same language-level reliability pattern as a reference-based metric. The contribution is operational: COMET-Kiwi-23 remains useful when trusted references are unavailable. The outliers show where references still change the conclusion and deserve closer study.

## Would plotting language pairs separately by direction help?

Yes. Separating directions is what reveals the main pattern. A stronger follow-up would use the same language, domain, systems, and annotation protocol in both directions so that direction is the primary changing factor.

## Do the results hold across morphological types?

The directional pattern appears in both agglutinative and fusional groups. Morphology has a smaller main effect than direction and may help narrow the choice among neural metrics, but the profile-level rankings are exploratory. English-to-Chinese was scored after the benchmark analysis and is not included in the displayed comparison. Its exploratory COMET correlation is .510.

Definitions:

- Agglutinative languages build words by stacking relatively distinct affixes. Examples include Turkish and Kazakh.
- Fusional languages use affixes that can express several grammatical features at once. Examples include German and Russian.
- Isolating languages rely more on separate words and word order. Examples include Chinese and Thai.

## What should we conclude about Ukrainian?

Treat it as an outlier linked to low-signal WMT22 crowd labels, not as proof of a domain effect. Same-year Czech-to-English data, which are mostly news, are also near zero. That weakens the earlier domain-mismatch explanation.

## What is the point of the Russian example?

It shows why pooling years can hide metric reliability. COMET correlates more strongly with human judgments within WMT21 and within WMT22 than in the combined data because the years contain different system generations and average quality levels. This is Simpson's Paradox.

## How should I describe the synthetic MQM tier?

Call it exploratory. Seven languages use NLLB translation hypotheses and Llama-generated MQM-style quality labels because comparable human annotations were unavailable. These results broaden coverage, but they still require validation against human judgments.

## What should I say about unusual points?

- Russian is the pooling example.
- Ukrainian and Czech suggest low-signal WMT22 crowd labels.
- Japanese BLEU requires language-appropriate tokenization. FLORES-200 SentencePiece tokenization raises the English-to-Japanese correlation from near zero to .238.
- Hebrew and Spanish are cases where reference-based COMET performs unusually well relative to COMET-Kiwi-23. Present them as observations unless a validated mechanism is available.

## How could the mechanisms be tested next?

Use matched bidirectional corpora, hold language and annotation protocol constant, compare in-domain and out-of-domain test sets, and measure vocabulary overlap or model perplexity. These controls would separate direction, domain, annotation quality, and dataset composition.

## How stable are the profile-level metric recommendations?

Treat the individual profile leaders as exploratory. Each cell contains only 2 to 9 languages, the leading neural metrics are often close, and the English-to-X fusional leader changes from COMET-Kiwi-23 under per-language voting to MetricX-24 under average correlation. The robust recommendation is to start with COMET-Kiwi-23 or MetricX-24 and validate on the target language.

## Did you test an ensemble?

Yes. The paper includes a min-max average of five neural metrics. It provides a useful general baseline, while a learned or profile-specific ensemble remains follow-up work.

## A clean poster walkthrough

1. Start with the research question and benchmark scale.
2. Define the three annotation tiers and identify the synthetic tier as exploratory.
3. Explain the direction graph, including the arrow notation and morphology terms.
4. Use Russian to show why year-level stratification matters.
5. Show that neural and reference-free metrics are competitive.
6. End with the metric-selection guide and three takeaways.
