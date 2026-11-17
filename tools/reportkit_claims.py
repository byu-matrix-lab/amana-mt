"""reportkit claims registry for the corrected AmanaMT paper (v2, 2026-11-10).

Each Claim binds a sentence in arxiv_submission/main.tex to a predicate over
results/paper_stats.json: while the predicate holds the sentence must be there;
once the data stops supporting it, the sentence must go. The Retracted entries pin
wording withdrawn from the published version so it cannot come back, except in a
paragraph that reports it as withdrawn ("original version", "corrected version").

Run from the repo root:
    PYTHONPATH=../../reportkit/src python3 -m reportkit claims
"""
import re

from reportkit.ssot.claims import Cased, Claim, Retracted


def v(d, key):
    return float(d["stats"][key]["value"])


TIERS = ("High", "Med", "Low")
SINGLE = ("BLEU", "ChrF", "BERTScore", "COMET", "xCOMET", "MetricX", "KiwiXXII", "KiwiXXIII")
NEURAL = ("COMET", "xCOMET", "MetricX", "KiwiXXII", "KiwiXXIII")
MQM_LANGS = ("DE", "RU", "ZH", "HE", "ES")
YEARS = ("Twenty", "TwentyOne", "TwentyTwo", "TwentyThree")
# A paragraph that reports a withdrawn finding as withdrawn may name it.
HEDGES = [re.compile(r"original version|corrected version|originally published|mislabel"),
          re.compile(r"\\textbf\{(?:Withdrawn|Corrected)\.\}")]   # the version-note box paragraphs


def _metricx_best_every_tier(d):
    return all(v(d, f"TierMetricX{t}Rho") >= max(v(d, f"Tier{m}{t}Rho") for m in SINGLE
                                                 if f"Tier{m}{t}Rho" in d["stats"])
               for t in TIERS)


CLAIMS = [
    # ---- claims the text makes, bound to the data ----
    Claim("metricx-best-every-tier", _metricx_best_every_tier,
          require=["MetricX-24 has the highest mean correlation in every tier"],
          why="tier means are computed; the superlative is typed"),
    Claim("high-over-medium-neural",
          lambda d: all(v(d, f"Tier{m}HighRho") > v(d, f"Tier{m}MedRho") for m in NEURAL),
          require=["For every neural metric, the High tier has the higher mean correlation"],
          why="reversed after the 2026-11-09 label fixes; must not silently flip back"),
    Claim("lexical-slightly-higher-medium",
          lambda d: all(v(d, f"Tier{m}MedRho") > v(d, f"Tier{m}HighRho") for m in ("BLEU", "ChrF", "BERTScore")),
          require=["BLEU, ChrF++ and BERTScore are slightly higher in Medium"]),
    Claim("direction-over-morph-under-da", lambda d: v(d, "EtaSqDir") > 2 * v(d, "EtaSqMorph"),
          require=["well ahead of morphological type"]),
    Claim("da-gap-positive-all-years",
          lambda d: all(v(d, f"MqmCtrlGapDA{y}CIlo") > 0 for y in YEARS),
          require=["Under DA the gap is positive in all"]),
    Claim("mqm-gap-not-consistent",
          lambda d: v(d, "MqmCtrlNNegMQM") >= 2,
          require=["does not replicate consistently under expert MQM"],
          why="the headline retraction depends on the sign flips under MQM"),
    Claim("zh22-crowd-da-collapse",
          lambda d: v(d, "MqmCtrlZhTwentyTwoCOMETCrowdDA") < 0.1 < v(d, "MqmCtrlZhTwentyTwoCOMETMQM") - 0.3,
          require=["The likelier cause is therefore the label"]),
    Claim("russian-pooled-within-years",
          lambda d: v(d, "RuRangeLo") <= v(d, "LangCOMETRU") <= v(d, "RuRangeHi"),
          require=["lies between its per-year values"]),
    Claim("spanish-weakest-mqm",
          lambda d: all(v(d, f"Lang{m}ES") == min(v(d, f"Lang{m}{l}") for l in MQM_LANGS)
                        for m in ("COMET", "MetricX")),
          require=["has the weakest COMET and MetricX correlations of the five MQM languages"]),
    Claim("hebrew-xcomet-strongest",
          lambda d: v(d, "LangXCOMETHE") > max(v(d, k) for k in
                    ("LangMetricXHE", "LangCOMETHE", "LangKiwiHE", "LangKiwiXXIIIHE", "LangBERTScoreHE")),
          require=["xCOMET has the strongest correlation"]),
    Claim("mixed-model-morph-significant", lambda d: v(d, "MixedModelMorphFusionalP") < 0.05,
          require=["smaller but also significant"]),
    Claim("yearstrat-unchanged",
          lambda d: abs(v(d, "YearStratEntoXFusionalPooled") - v(d, "YearStratEntoXFusionalStrat")) < 0.01,
          require=["essentially unchanged"]),
    Claim("ck23-agglutinative-xtoen-usually",
          lambda d: v(d, "WinXtoEnAgglutin") / v(d, "WinTotalXtoEnAgglutin") > 0.5
                    and v(d, "WinXtoEnFusional") / v(d, "WinTotalXtoEnFusional") <= 0.5,
          require=["CometKiwi-23 usually wins agglutinative pairs; fusional is split"]),
    Claim("metricx-wins-all-pivot", lambda d: v(d, "PivotMetricXWins") == v(d, "PivotN"),
          require=[re.compile(r"and all X\W{0,20}Y pairs")]),
    Claim("oos-metricx-not-best",
          lambda d: v(d, "LangXCOMETHE") >= v(d, "LangMetricXHE") and v(d, "LangXCOMETES") >= v(d, "LangMetricXES"),
          require=["On these, MetricX-24 is not the best"],
          why="the out-of-sample check (WMT23 he-en, WMT24 en-es) is what qualifies the MetricX-best claim"),
    # ---- wording withdrawn from the published version ----
    Retracted("simpson", re.compile(r"simpson'?s paradox"), unless=HEDGES, scope="paragraph",
              why="Russian's pooled rho was a scale-mixing artifact"),
    Retracted("medium-over-high", re.compile(r"medium\s*\$?>\$?\s*high|medium-resource languages (?:outperform|are better evaluated)"),
              unless=HEDGES, scope="paragraph", why="reversed after the label fixes"),
    Retracted("spanish-strongest", re.compile(r"strongest correlations of any MQM language|best-evaluated MQM language"),
              unless=HEDGES, scope="paragraph"),
    Retracted("ukrainian-domain", re.compile(r"domain (?:confound|mismatch|outlier)"), unless=HEDGES, scope="paragraph",
              why="cs-en/zh-en WMT22 crowd DA collapse too; it is the label"),
    Retracted("non-news", "non-news", why="Ukrainian was the only non-news language"),
    Retracted("direction-predicts", re.compile(r"direction (?:itself )?predicts (?:automatic )?metric reliability"),
              unless=HEDGES + [re.compile(r"do not claim")], scope="paragraph"),
    Retracted("metricx-all-but-two", "all but two languages"),
    Retracted("ck23-consistent", "wins consistently"),
    Retracted("no-isolating-data", re.compile(r"there are no Tier-1 en"),
              why="en->zh existed and was dropped by a config rule"),
    Retracted("spa-standard", re.compile(r"soft pairwise accuracy"),
              unless=[re.compile(r"not the system-level soft pairwise accuracy")], scope="paragraph",
              why="the statistic is segment-level tie-credited PA, not SPA"),
    Retracted("gemba", Cased(r"GEMBA(?!-MQM)"), unless=[re.compile(r"removed GEMBA"), re.compile(r"\\textbf\{Corrected\.\}")],
              scope="paragraph", why="degenerate scores; removed"),
    Retracted("textbook", "textbook"),
    Retracted("ck23-abbrev", Cased(r"\bCK-?23\b"), why="author preference: always write CometKiwi-23"),
    Retracted("confirming-prediction", re.compile(r"confirming (?:the )?prediction")),
]
