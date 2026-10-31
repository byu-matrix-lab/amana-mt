# AmanaMT poster boaster script

Target length: 2 minutes. This is the memorization draft.

## Slide 1 | 0:00–0:25

Quick question: when COMET or BLEU gives your translation system a better score, can you trust it?

For a decade, the Workshop on Machine Translation, or WMT, has compared automatic metrics with human judgments. AmanaMT combines those shared tasks with additional annotations. It covers more than 730,000 segments, 33 languages, and ten metrics. Seven languages use exploratory synthetic quality labels.

## Slide 2 | 0:25–0:55

We expected morphology to be the largest predictor of metric reliability. It was not. Translation direction was.

Here, English-to-X means English is the source. X-to-English means English is the target.

In both groups, metrics agree with people more strongly when translating from English than when translating into English. Direction explains more than four times as much variation as morphology.

Morphology may help narrow the choice among neural metrics, but the profile-level rankings are exploratory.

## Slide 3 | 0:55–1:35

Russian shows why the year of evaluation matters.

COMET has a clear positive relationship with human judgments within WMT 2021. It is even stronger within WMT 2022. But the correlation becomes much weaker when we combine the years.

This is Simpson's Paradox. The years contain different system generations and average quality. Pooling shifts their relative positions and hides the stronger within-year pattern. We should compare systems within each year before interpreting aggregate results.

## Slide 4 | 1:35–2:00

Before trusting an MT score, check three things: translation direction, the quality of the human labels, and whether different years were pooled.

Neural metrics such as COMET, COMET-Kiwi-23, and MetricX align with people better than surface-overlap metrics such as BLEU and ChrF++.

Come see the AmanaMT poster for the full benchmark and an exploratory metric guide. I am Isaac Thompson from the BYU MATRIX Lab. Thank you.

## Delivery notes

- Pause briefly after the opening question.
- Memorize the first sentence after every slide change.
- Pause after “Translation direction.”
- On slide 2, trace the pair of bars in each morphology group.
- On slide 3, point to WMT21, WMT22, then Pooled as you narrate the change.
- Say “Simpson's Paradox” slowly, then give the plain-language explanation.
- Use a full speaking voice, avoid vocal fry, and finish final consonants.
- Say “W-M-T” as three letters. Keep a steady pace for non-native English listeners.
