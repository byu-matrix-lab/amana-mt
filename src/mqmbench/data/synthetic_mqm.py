"""Generate synthetic span-level MQM annotations using a local LLM.

Uses GEMBA-MQM style three-shot prompting via a HuggingFace text-generation
model. Designed to run on the BYU supercomputer with HF_HUB_OFFLINE=1.
Results are cached to JSONL files so the model only runs once per language.
"""

import gc
import logging
import re
from pathlib import Path

import pandas as pd
from transformers import pipeline as hf_pipeline

from mqmbench.constants import AnnotationTier
from mqmbench.data.utils import read_jsonl_cache, write_jsonl_cache

logger = logging.getLogger(__name__)

_LANG_NAMES = {
    "sw": "Swahili", "ht": "Haitian Creole", "lo": "Lao", "th": "Thai",
    "my": "Burmese", "am": "Amharic", "ka": "Georgian",
}

PROMPT_TEMPLATE = """You are a strict professional translation reviewer. Machine translations almost always contain errors — mistranslations, omissions, fluency problems, or word-choice issues. Your job is to find them. Be critical.

Evaluate the translation from English to {target_lang}.

=== EXAMPLES ===

Source: The patient must take the medication twice daily with food.
Translation (French): Le patient devra prendre le médicament deux fois par jour.
Review:
ERROR: [severity: minor] [category: omission] [span: par jour]

Source: The government announced new economic reforms to combat inflation.
Translation (Swahili): Serikali ilitangaza mageuzi ya uchumi kupambana na mfumko.
Review:
ERROR: [severity: minor] [category: omission] [span: kupambana na mfumko]

Source: Scientists discovered a new species of deep-sea fish near the Mariana Trench.
Translation (Spanish): Los científicos descubrieron una nueva especie de pez de aguas profundas cerca de la Fosa de las Marianas.
Review:
NO ERRORS

Source: The contract will expire at the end of the fiscal year unless renewed.
Translation (Amharic): ውሉ እስካልታደሰ ድረስ በዓመቱ መጨረሻ ያበቃል።
Review:
ERROR: [severity: major] [category: mistranslation] [span: በዓመቱ መጨረሻ]

=== YOUR TASK ===

Source: {source}
Translation ({target_lang}): {hypothesis}

Review (list ALL errors found, or output NO ERRORS only if the translation is genuinely perfect):"""

_ERROR_PATTERN = re.compile(
    r"ERROR:\s*\[severity:\s*(major|minor)\]\s*"
    r"\[category:\s*([^\]]+)\]\s*\[span:\s*([^\]]+)\]",
    re.IGNORECASE,
)


def _parse_output(text: str, base_info: dict) -> list[dict]:
    """Parse LLM output into span-level annotation rows."""
    if "NO ERRORS" in text.upper():
        row = dict(base_info)
        row.update({"error_type": "no_error", "severity": "no_error",
                    "error_start": -1, "error_end": -1})
        return [row]

    rows = []
    for match in _ERROR_PATTERN.finditer(text):
        sev, cat, span = match.groups()
        hyp = base_info["hypothesis"]
        start_idx = hyp.find(span.strip())
        end_idx = start_idx + len(span.strip()) if start_idx != -1 else -1
        row = dict(base_info)
        row.update({
            "severity": sev.strip().lower(),
            "error_type": cat.strip().lower(),
            "error_start": start_idx,
            "error_end": end_idx,
        })
        rows.append(row)

    if not rows:
        row = dict(base_info)
        row.update({"error_type": "no_error", "severity": "no_error",
                    "error_start": -1, "error_end": -1})
        rows.append(row)

    return rows


def generate_synthetic_mqm(
    segments_df: pd.DataFrame,
    model_name: str,
    cache_dir: str = "data/cache",
    batch_size: int = 4,
) -> pd.DataFrame:
    """Generate GEMBA-MQM style annotations using a local HuggingFace LLM.

    Args:
        segments_df: DataFrame with columns: segment_id, source, hypothesis,
                     reference, lang.
        model_name: HuggingFace model ID (e.g. 'meta-llama/Llama-3.1-8B-Instruct').
                    Must be pre-downloaded; run with HF_HUB_OFFLINE=1 on compute nodes.
        cache_dir: Directory for cached JSONL annotation files.
        batch_size: Prompts per forward pass.

    Returns:
        DataFrame with span-level annotation rows compatible with converter.py.
        Tagged with annotation_tier = AnnotationTier.SYNTHETIC_MQM.
    """
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    langs = segments_df["lang"].unique().tolist()
    cache_files = {lang: cache_path / f"synthetic_mqm_{lang}.jsonl" for lang in langs}
    langs_to_annotate = [lang for lang in langs if not cache_files[lang].exists()]

    span_rows = []

    for lang in langs:
        if cache_files[lang].exists():
            logger.info(f"Loading cached synthetic MQM for {lang}")
            span_rows.extend(read_jsonl_cache(cache_files[lang]))

    if langs_to_annotate:
        logger.info(f"Loading local LLM for synthetic MQM: {model_name}")
        pipe = hf_pipeline("text-generation", model=model_name,
                           max_new_tokens=64, do_sample=True, temperature=0.3,
                           return_full_text=False,
                           batch_size=32)
        pipe.tokenizer.pad_token = pipe.tokenizer.eos_token
        pipe.tokenizer.padding_side = "left"

        for lang in langs_to_annotate:
            group = segments_df[segments_df["lang"] == lang]
            logger.info(f"Generating synthetic MQM for {lang} ({len(group)} segments)...")
            rows_list = group.to_dict(orient="records")

            lang_name = _LANG_NAMES.get(lang, lang)
            prompts = [
                PROMPT_TEMPLATE.format(
                    target_lang=lang_name,
                    source=row["source"],
                    hypothesis=row["hypothesis"],
                )
                for row in rows_list
            ]

            outputs = list(pipe(prompts))

            lang_rows = []
            for row, out in zip(rows_list, outputs):
                base_info = {
                    "segment_id": row["segment_id"],
                    "source": row["source"],
                    "hypothesis": row["hypothesis"],
                    "reference": row["reference"],
                    "lang": lang,
                    "annotation_tier": AnnotationTier.SYNTHETIC_MQM,
                }
                lang_rows.extend(_parse_output(out[0]["generated_text"], base_info))

            write_jsonl_cache(cache_files[lang], lang_rows)
            span_rows.extend(lang_rows)

        # Free the LLM from GPU and CPU memory before returning; the caller
        # will load separate neural MT metric models (xCOMET, COMET-Kiwi, etc.)
        # and keeping the LLM alive causes OOM.
        del pipe
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    return pd.DataFrame(span_rows)
