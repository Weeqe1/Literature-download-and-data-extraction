# etl_ensemble/consensus_engine.py
"""Utilities to compare outputs from multiple models and decide agreement.
Field-wise comparison with dynamic numeric tolerances based on field type/units.
"""
import math
import json
import re
from typing import Dict, Any, List, Tuple, Optional

# Field-specific tolerance configuration
# Fields not listed here use default tolerances
FIELD_TOLERANCE_CONFIG: Dict[str, Dict[str, float]] = {
    # Size fields (nm) - small values, need tight tolerance
    "size_nm": {"rel_tol": 0.05, "abs_tol": 0.5},
    "core_diameter_nm": {"rel_tol": 0.05, "abs_tol": 0.5},
    "shell_thickness_nm": {"rel_tol": 0.05, "abs_tol": 0.5},
    "total_diameter_nm": {"rel_tol": 0.05, "abs_tol": 0.5},
    "length_nm": {"rel_tol": 0.05, "abs_tol": 0.5},
    "hydrodynamic_diameter_nm": {"rel_tol": 0.05, "abs_tol": 1.0},
    # Wavelength fields (nm) - larger values, looser absolute tolerance
    "excitation_wavelength_nm": {"rel_tol": 0.01, "abs_tol": 5.0},
    "emission_wavelength_nm": {"rel_tol": 0.01, "abs_tol": 5.0},
    "absorption_peak_nm": {"rel_tol": 0.01, "abs_tol": 5.0},
    "stokes_shift_nm": {"rel_tol": 0.02, "abs_tol": 5.0},
    # Percentage fields
    "quantum_yield_percent": {"rel_tol": 0.05, "abs_tol": 1.0},
    "dopant_concentration_percent": {"rel_tol": 0.05, "abs_tol": 0.5},
    "cell_viability_percent": {"rel_tol": 0.05, "abs_tol": 2.0},
    # Time fields (ns, min, s, h)
    "fluorescence_lifetime_ns": {"rel_tol": 0.05, "abs_tol": 0.5},
    "photostability_half_life_min": {"rel_tol": 0.10, "abs_tol": 5.0},
    "response_time_s": {"rel_tol": 0.10, "abs_tol": 1.0},
    # Potential (mV)
    "zeta_potential_mV": {"rel_tol": 0.10, "abs_tol": 2.0},
    # Temperature (C)
    "reaction_temperature_C": {"rel_tol": 0.02, "abs_tol": 5.0},
    "thermal_stability_max_C": {"rel_tol": 0.02, "abs_tol": 5.0},
}


def get_field_tolerance(field_name: str, default_rel: float = 0.01, default_abs: float = 1.0) -> Tuple[float, float]:
    """Get tolerance for a specific field based on FIELD_TOLERANCE_CONFIG.
    
    Args:
        field_name: The field name to look up
        default_rel: Default relative tolerance if not in config
        default_abs: Default absolute tolerance if not in config
        
    Returns:
        Tuple of (rel_tol, abs_tol)
    """
    config = FIELD_TOLERANCE_CONFIG.get(field_name, {})
    return config.get("rel_tol", default_rel), config.get("abs_tol", default_abs)


def is_number(x: Any) -> bool:
    """Check if value can be converted to float."""
    try:
        float(x)
        return True
    except (ValueError, TypeError):
        return False


def numeric_close(a: Any, b: Any, rel_tol: float = 0.01, abs_tol: float = 1.0) -> bool:
    """Check if two numeric values are close within tolerance."""
    try:
        a = float(a)
        b = float(b)
    except (ValueError, TypeError):
        return False
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)

def compare_field_values(
    vals: List[Dict[str, Any]],
    field_name: Optional[str] = None,
    numeric_rel: float = 0.01,
    numeric_abs: float = 1.0
) -> Tuple[bool, Any, Dict[str, Any]]:
    """Compare values from multiple models for a single field.
    
    Args:
        vals: list of {model_id, value, resp, field}
        field_name: Field name for dynamic tolerance lookup
        numeric_rel: Fallback relative tolerance
        numeric_abs: Fallback absolute tolerance
        
    Returns:
        Tuple of (agree:bool, agreed_value or None, details dict)
    """
    # Get field-specific tolerance if available
    if field_name:
        rel_tol, abs_tol = get_field_tolerance(field_name, numeric_rel, numeric_abs)
    else:
        rel_tol, abs_tol = numeric_rel, numeric_abs
    
    # Collect non-null values from model responses
    cleaned = []
    for v in vals:
        value = None
        resp = v.get('resp')
        if not isinstance(resp, dict):
            continue
            
        # Skip models that returned an error
        if resp.get('error'):
            continue
            
        # Try structured response format: {field: {value: ...}}
        field_key = v.get('field')
        if field_key and isinstance(resp.get(field_key), dict) and 'value' in resp[field_key]:
            value = resp[field_key]['value']
        else:
            # Fallback: direct value in resp or in val dict
            value = v.get('value') if 'value' in v else (resp.get(field_key) if field_key else None)
            
        if value is None:
            continue
        cleaned.append({'model_id': v.get('model_id'), 'value': value, 'raw': v})

    if not cleaned:
        return False, None, {'reason': 'no_values'}

    # Numeric comparison
    if all(is_number(x['value']) for x in cleaned):
        base = float(cleaned[0]['value'])
        agree = all(
            numeric_close(base, float(x['value']), rel_tol=rel_tol, abs_tol=abs_tol)
            for x in cleaned[1:]
        )
        if agree:
            return True, base, {'method': 'numeric', 'rel_tol': rel_tol, 'abs_tol': abs_tol}
        else:
            return False, None, {
                'method': 'numeric_disagree',
                'samples': cleaned,
                'tolerance_used': {'rel_tol': rel_tol, 'abs_tol': abs_tol}
            }
    else:
        # String comparison: normalized exact match (case-insensitive, whitespace-normalized)
        def normalize(s: Any) -> str:
            return re.sub(r'\s+', ' ', str(s).strip().lower())
        
        first = normalize(cleaned[0]['value'])
        agree = all(normalize(x['value']) == first for x in cleaned[1:])
        
        if agree:
            return True, cleaned[0]['value'], {'method': 'string'}
        else:
            return False, None, {'method': 'string_disagree', 'samples': cleaned}

def compare_outputs(
    model_results: List[Dict[str, Any]],
    thresholds: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Compare outputs from multiple models and determine agreement per field.
    
    Args:
        model_results: list of dicts with 'model_id' and 'resp' (dict of fields)
        thresholds: Optional override for default tolerances
        
    Returns:
        Dict with 'agreed' and 'disagreed' field mappings
    """
    if thresholds is None:
        thresholds = {'numeric_relative_tol': 0.01, 'numeric_abs_tol': 1.0}

    default_rel = thresholds.get('numeric_relative_tol', 0.01)
    default_abs = thresholds.get('numeric_abs_tol', 1.0)

    # Aggregate all field names from all model responses
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
            vals.append({'model_id': model_id, 'field': f, 'value': None, 'resp': resp})
        
        ok, v, details = compare_field_values(
            vals,
            field_name=f,
            numeric_rel=default_rel,
            numeric_abs=default_abs
        )
        
        if ok:
            agreed[f] = {'value': v, 'evidence': vals}
        else:
            disagreed[f] = {'candidates': vals, 'details': details}
    
    return {'agreed': agreed, 'disagreed': disagreed}
