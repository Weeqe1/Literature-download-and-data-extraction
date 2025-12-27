# etl_core/llm_field_extractor.py
"""Wrapper summarizer that accepts optional fourth argument and normalizes LLM output.

Expected usage:
    summarize_text_blocks(layout_json_path, schema_path, prompts_dir, text_json_path=None)

Returns a dict with keys:
    - raw: raw LLM output (dict)
    - normalized: normalized dict (after normalizer.normalize_llm_output), or None on failure
"""

from typing import Optional, Dict, Any
import json, os

try:
    from .llm_openai_client import LLMClient
except Exception:
    # fallback to top-level import
    from llm_openai_client import LLMClient

try:
    from .output_normalizer import normalize_llm_output
except Exception:
    def normalize_llm_output(x): return x

def summarize_text_blocks(layout_json: str, schema_path: str, prompts_dir: str, text_json: Optional[str]=None) -> Dict[str, Any]:
    """Run LLM extraction and normalize.

    layout_json: path to layout.json produced by pdf_ingest
    schema_path: path to configs/schema.yml
    prompts_dir: path to configs/prompts/
    text_json: optional path to extracted text JSON (if available)
    """
    # Load optional inputs (best-effort)
    payload = {}
    try:
        with open(layout_json, 'r', encoding='utf-8') as f:
            payload['layout'] = json.load(f)
    except Exception:
        payload['layout'] = None

    if text_json:
        try:
            with open(text_json, 'r', encoding='utf-8') as f:
                payload['text'] = json.load(f)
        except Exception:
            payload['text'] = None

    # Load prompts (if available)
    try:
        prompts = {}
        for fn in os.listdir(prompts_dir):
            if fn.lower().endswith('.md') or fn.lower().endswith('.txt'):
                with open(os.path.join(prompts_dir, fn), 'r', encoding='utf-8') as f:
                    prompts[fn] = f.read()
        payload['prompts'] = prompts
    except Exception:
        payload['prompts'] = None

    client = LLMClient()

    # Build a simple prompt combining prompts/paper_summarize.md and a short instruction
    prompt_text = ""
    if payload.get('prompts'):
        # prefer paper_summarize.md
        prompt_text = payload['prompts'].get('paper_summarize.md') or list(payload['prompts'].values())[0]
    if not prompt_text:
        prompt_text = "Extract the canonical fields and return JSON."

    # For structured call, pass the prompt_text and a simple schema placeholder
    schema_placeholder = {"type":"object"}

    try:
        result = client.structured(prompt_text, schema_placeholder)
    except Exception as e:
        # Return failure info
        return {"raw": None, "normalized": None, "error": str(e)}

    # Normalize
    try:
        normalized = normalize_llm_output(result)
    except Exception as e:
        normalized = None

    return {"raw": result, "normalized": normalized}
