
import json, re
from typing import Any, Dict

def parse_maybe_json(x):
    if isinstance(x, (dict, list)):
        return x
    if not isinstance(x, str):
        return x
    s = x.strip()
    if not s:
        return None
    if (s.startswith('{') and s.endswith('}')) or (s.startswith('[') and s.endswith(']')):
        try:
            return json.loads(s)
        except Exception:
            return x
    return x

def coerce_float(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s in ('', 'null', 'None', 'NaN', 'nan'):
        return None
    s = s.replace('%', '').replace(',', '')
    try:
        return float(s)
    except Exception:
        m = re.search(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', s)
        if m:
            try:
                return float(m.group(0))
            except Exception:
                return None
        return None

def normalize_units(row: Dict[str, Any]) -> Dict[str, Any]:
    qy = row.get('QY', None)
    qy_f = coerce_float(qy)
    if qy_f is not None and qy_f <= 1.0:
        qy_f = qy_f * 100.0
    row['QY'] = qy_f

    abs_nm = coerce_float(row.get('abs_peak_nm', None))
    emi_nm = coerce_float(row.get('emi_peak_nm', None))
    stokes = coerce_float(row.get('stokes_nm', None))
    if stokes is None and (abs_nm is not None and emi_nm is not None):
        stokes = emi_nm - abs_nm
    row['abs_peak_nm'] = abs_nm
    row['emi_peak_nm'] = emi_nm
    row['stokes_nm'] = stokes

    for fld in ['lifetime_ns','core_size_nm','shell_thickness_nm','zeta_mV','hydrodynamic_diameter_nm','PDI','photobleach_t_half_min','brightness','SBR']:
        if fld in row:
            row[fld] = coerce_float(row.get(fld))

    return row
