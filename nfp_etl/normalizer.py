# nfp_etl/normalizer.py
"""Normalize LLM output: alias mapping, canonicalization, numeric coercion, provenance handling"""
import re, json, os

# load aliases if present
ALIASES = {}
try:
    import yaml
    alias_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'aliases.yml')
    alias_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'configs', 'aliases.yml'))
    if os.path.exists(alias_path):
        with open(alias_path, 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f) or {}
            ALIASES = loaded.get('aliases', {})
except Exception:
    ALIASES = {}

ALIAS_TO_CANON = {}
for canon, lst in ALIASES.items():
    if isinstance(lst, list):
        for a in lst:
            ALIAS_TO_CANON[str(a).strip().lower()] = canon

MANUAL = {'plqy':'QY','φf':'QY','phi':'QY','lambda_em':'emi_peak_nm','lambda_abs':'abs_peak_nm'}
for k,v in MANUAL.items():
    ALIAS_TO_CANON.setdefault(k, v)

def canonical_name(name):
    if name is None:
        return name
    n = str(name).strip()
    key = n.lower()
    if key in ALIAS_TO_CANON:
        return ALIAS_TO_CANON[key]
    s = re.sub(r'[^a-z0-9]', '', key)
    for a,k in ALIAS_TO_CANON.items():
        if re.sub(r'[^a-z0-9]', '', a) == s:
            return k
    return n

def coerce_value(field, value):
    if value is None:
        return None
    if isinstance(value, dict) and 'value' in value:
        value = value.get('value')
    s = str(value).strip()
    if s == '':
        return None
    if '%' in s:
        try:
            return float(s.replace('%','').strip())
        except:
            pass
    m = re.search(r'([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)', s)
    if m:
        try:
            num = float(m.group(1))
        except:
            return None
        fname = (field or '').lower()
        if 'qy' in fname or 'quantum' in fname or 'plqy' in fname:
            if abs(num) <= 1.0:
                return float(num * 100.0)
            return float(num)
        return float(num)
    return value

def normalize_llm_output(llm_json):
    out = {}
    provenance = {}
    if not llm_json:
        return {}
    for k,v in llm_json.items():
        can = canonical_name(k)
        if isinstance(v, dict) and 'value' in v:
            val = v.get('value')
            src = v.get('_src')
        else:
            val = v
            src = None
        coerced = coerce_value(can, val)
        out[can] = coerced
        if src is not None:
            provenance[f"{can}__src"] = src
    merged = out.copy()
    merged.update(provenance)
    return merged
