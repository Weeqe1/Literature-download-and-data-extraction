# etl_ensemble/focused_reextractor.py
"""Focused re-extraction: given disagreements, ask models to re-extract focusing on those fields.
"""
from typing import List, Dict, Any
import textwrap, json

def build_focus_prompt(original_prompt: str, disagreement_fields: Dict[str,Any], snippets: Dict[str,str]=None):
    # Create a concise prompt asking the model to re-extract only the disputed fields
    fields = list(disagreement_fields.keys())
    s = textwrap.dedent(f"""    The previous extraction produced conflicting values for the following fields: {fields}
    Please re-examine the provided snippets and the PDF content and return JSON only with keys for these fields.
    For each key, return {{"value": ..., "_src": {{"page":int, "snippet":str, "confidence":float}}}}
    """)
    if snippets:
        for k, sn in snippets.items():
            s += "\n\n" + f"Field: {k} -- Context snippet: {sn}"
    s += "\n\nReturn JSON only."
    return s

def reextract(multi_client, model_ids: List[str], prompt_base: str, disagreement_fields: Dict[str,Any], snippets: Dict[str,str]=None, schema=None):
    results = []
    focus_prompt = build_focus_prompt(prompt_base, disagreement_fields, snippets=snippets)
    for mid in model_ids:
        out = multi_client.extract(mid, focus_prompt, schema=schema)
        results.append(out)
    return results
