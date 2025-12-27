# etl_ensemble/consensus_engine.py
"""Utilities to compare outputs from multiple models and decide agreement.
Simple field-wise comparison with numeric tolerances and exact match for strings.
"""
import math, json, re
from typing import Dict, Any, List, Tuple

def is_number(x):
    try:
        float(x)
        return True
    except Exception:
        return False

def numeric_close(a, b, rel_tol=0.01, abs_tol=1.0):
    try:
        a = float(a); b = float(b)
    except Exception:
        return False
    if math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol):
        return True
    return False

def compare_field_values(vals: List[Dict[str, Any]], numeric_rel=0.01, numeric_abs=1.0) -> Tuple[bool, Any, Dict[str,Any]]:
    """vals: list of {model_id, value, confidence?}
    Returns: (agree:boolean, agreed_value or None, details)
    """
    # collect non-null values
    cleaned = []
    for v in vals:
        value = None
        # handle structured resp where value may be nested
        resp = v.get('resp')
        if isinstance(resp, dict) and isinstance(resp.get(v.get('field')), dict) and 'value' in resp.get(v.get('field')):
            value = resp.get(v.get('field'))['value']
        else:
            # attempt to read v['value'] or resp[f]
            value = v.get('value') if 'value' in v else resp.get(v.get('field')) if isinstance(resp, dict) else resp
        if value is None:
            continue
        cleaned.append({'model_id': v.get('model_id'), 'value': value, 'raw': v})

    if not cleaned:
        return False, None, {'reason':'no_values'}

    # If all values are numbers -> numeric compare
    if all(is_number(x['value']) for x in cleaned):
        # try pairwise agreement
        base = float(cleaned[0]['value'])
        agree = all(numeric_close(base, float(x['value']), rel_tol=numeric_rel, abs_tol=numeric_abs) for x in cleaned[1:])
        if agree:
            return True, base, {'method':'numeric'}
        else:
            return False, None, {'method':'numeric_disagree', 'samples': cleaned}
    else:
        # string compare: exact normalized match (case-insensitive, strip)
        norm = lambda s: re.sub(r'\s+',' ', str(s).strip().lower())
        first = norm(cleaned[0]['value'])
        agree = all(norm(x['value']) == first for x in cleaned[1:])
        if agree:
            return True, cleaned[0]['value'], {'method':'string'}
        else:
            return False, None, {'method':'string_disagree', 'samples': cleaned}

def compare_outputs(model_results: List[Dict[str,Any]], thresholds: Dict[str,Any]=None) -> Dict[str,Any]:
    """model_results: list of outputs per model where each output contains model_id and resp (dict of fields)
    Returns dict with agreed_fields, disagreements
    """
    if thresholds is None:
        thresholds = {'numeric_relative_tol':0.01,'numeric_abs_tol':1.0}

    # aggregate field names
    fields = set()
    for mr in model_results:
        resp = mr.get('resp') or {}
        if isinstance(resp, dict):
            fields.update(resp.keys())
    agreed = {}
    disagreed = {}
    for f in sorted(fields):
        vals = []
        for mr in model_results:
            model_id = mr.get('model_id')
            resp = mr.get('resp') or {}
            # pass field name through value holder
            vals.append({'model_id': model_id, 'field': f, 'value': None, 'resp': resp})
        ok, v, details = compare_field_values(vals, numeric_rel=thresholds.get('numeric_relative_tol',0.01), numeric_abs=thresholds.get('numeric_abs_tol',1.0))
        if ok:
            agreed[f] = {'value': v, 'evidence': vals}
        else:
            disagreed[f] = {'candidates': vals, 'details': details}
    return {'agreed': agreed, 'disagreed': disagreed}
