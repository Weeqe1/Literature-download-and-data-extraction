import os
import sys
import json
import glob
import re
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np


def flatten_dict(d: Dict[str, Any], parent_key: str = "") -> Dict[str, Any]:
    """Flatten nested dict, extracting 'value' from consensus result dicts."""
    out = {}
    if not isinstance(d, dict):
        return out
    for k, v in d.items():
        key = f"{parent_key}__{k}" if parent_key else k
        if isinstance(v, dict):
            if "value" in v and len(v) <= 8:
                out[key] = v.get("value")
            else:
                out.update(flatten_dict(v, key))
        else:
            out[key] = v
    return out


def extract_numeric_range(value_str: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """Extract numeric range from string like '0.02 to 50.00 ng/mL' or '1.5-2.0 nm'.
    
    Args:
        value_str: String potentially containing a numeric range with units
        
    Returns:
        Tuple of (low_value, high_value, units) or (None, None, original_string) if not parseable
    """
    if not isinstance(value_str, str):
        return None, None, None
    
    s = value_str.strip()
    
    # Pattern: "number [- to ~] number unit"
    # Matches: "0.02 to 50.00 ng/mL", "1.5-2.0 nm", "100 ~ 500 nM"
    range_pattern = re.compile(
        r'([+-]?\d+\.?\d*)\s*(?:-|to|~|–)\s*([+-]?\d+\.?\d*)\s*([a-zA-Z/%°μµ]+(?:/[a-zA-Z]+)?)?'
    )
    match = range_pattern.search(s)
    if match:
        low = float(match.group(1))
        high = float(match.group(2))
        unit = match.group(3) if match.group(3) else ""
        return low, high, unit
    
    # Pattern: single number with unit
    single_pattern = re.compile(r'([+-]?\d+\.?\d*)\s*([a-zA-Z/%°μµ]+(?:/[a-zA-Z]+)?)?')
    match = single_pattern.search(s)
    if match:
        val = float(match.group(1))
        unit = match.group(2) if match.group(2) else ""
        return val, val, unit
    
    return None, None, s


def extract_lod_value(lod_str: str) -> Tuple[Optional[float], Optional[str]]:
    """Extract LOD numeric value and unit from string.
    
    Args:
        lod_str: LOD string like "0.003 ng/mL" or "< 0.057 μg/mL"
        
    Returns:
        Tuple of (numeric_value, unit_string)
    """
    if not isinstance(lod_str, str):
        return None, None
    
    s = lod_str.strip()
    # Remove leading < > ≤ ≥ symbols
    s = re.sub(r'^[<>≤≥]\s*', '', s)
    
    pattern = re.compile(r'(\d+\.?\d*(?:[eE][+-]?\d+)?)\s*([a-zA-Z/%°μµ]+(?:/[a-zA-Z]+)?)?')
    match = pattern.search(s)
    if match:
        val = float(match.group(1))
        unit = match.group(2) if match.group(2) else ""
        return val, unit
    return None, s


def clean_numeric_field(value: Any) -> Optional[float]:
    """Safely convert value to float, handling various string formats."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s or s.lower() in ('null', 'none', 'n/a', 'not specified', ''):
            return None
        # Remove common non-numeric prefixes/suffixes
        s = re.sub(r'^[<>≤≥~≈]\s*', '', s)
        s = re.sub(r'\s*[a-zA-Z/%°μµ]+(?:/[a-zA-Z]+)?$', '', s)
        try:
            return float(s)
        except ValueError:
            return None
    return None


def build_dataset(json_dir: str = 'outputs/extraction', out_path: str = 'outputs/nfp_ml_ready_dataset.csv'):
    """Build ML-ready dataset from extracted JSON files with enhanced data cleaning."""
    print(f"\n[Post-Processing] Building ML-ready dataset from {json_dir}...")
    json_files = glob.glob(os.path.join(json_dir, "*.json"))
    
    if not json_files:
        print("No JSON files found.")
        return
    
    rows = []
    for jf in json_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            paper_meta = data.get("paper_metadata", {})
            samples = data.get("samples", [])
            
            for s in samples:
                if not isinstance(s, dict):
                    continue
                    
                # Merge sample data and paper metadata
                merged = s.copy()
                for k, v in paper_meta.items():
                    merged[f"paper_{k}"] = v
                
                flat = flatten_dict(merged)
                
                # Enhanced numeric cleaning for known numeric fields
                numeric_fields = [
                    'size_nm', 'core_diameter_nm', 'total_diameter_nm', 'length_nm',
                    'excitation_wavelength_nm', 'emission_wavelength_nm',
                    'quantum_yield_percent', 'fluorescence_lifetime_ns',
                    'zeta_potential_mV', 'hydrodynamic_diameter_nm',
                    'detection_limit'
                ]
                for nf in numeric_fields:
                    if nf in flat:
                        flat[nf] = clean_numeric_field(flat[nf])
                
                # Extract range fields into separate low/high columns
                range_fields = ['linear_range']
                for rf in range_fields:
                    if rf in flat and isinstance(flat[rf], str):
                        low, high, unit = extract_numeric_range(flat[rf])
                        if low is not None:
                            flat[f'{rf}_low'] = low
                            flat[f'{rf}_high'] = high
                            if unit:
                                flat[f'{rf}_unit'] = unit
                
                flat['_source_file'] = os.path.basename(jf)
                rows.append(flat)
        except json.JSONDecodeError as e:
            print(f"Error parsing {jf}: {e}")
        except IOError as e:
            print(f"Error reading {jf}: {e}")
            
    if not rows:
        print("No data to process.")
        return
        
    df = pd.DataFrame(rows)
    
    mandatory = [
        'core_material', 
        'emission_wavelength_nm', 
        'target_analyte'
    ]
    
    # Store found column names to filter
    filter_cols = []
    for m in mandatory:
        match_cols = [c for c in df.columns if m.lower() in c.lower()]
        if not match_cols:
            filter_cols.append(m)
            df[m] = np.nan
        else:
            # Pick the first matching column that has the most non-null values
            best_col = sorted(match_cols, key=lambda c: df[c].notna().sum(), reverse=True)[0]
            filter_cols.append(best_col)
            
    before_count = len(df)
    for m in filter_cols:
        df = df[df[m].notna() & (df[m].astype(str).str.strip() != "")]
        
    print(f"  Filtering: Removed {before_count - len(df)} records missing mandatory fields.")
    
    # Clean remaining columns
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        df[col] = df[col].fillna("Not Specified")
        df[col] = df[col].replace(r'^\s*$', "Not Specified", regex=True)

    # Ensure output directory exists
    try:
        os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    except OSError as e:
        print(f"Error creating output directory: {e}")
        return
    
    try:
        df.to_csv(out_path, index=False, encoding='utf-8-sig')
        print(f"  Success: Saved ML-ready dataset with {len(df)} records to {out_path}")
    except IOError as e:
        print(f"Error saving dataset: {e}")


if __name__ == '__main__':
    in_dir = sys.argv[1] if len(sys.argv) > 1 else 'outputs/extraction'
    out_file = sys.argv[2] if len(sys.argv) > 2 else 'outputs/nfp_ml_ready_dataset.csv'
    build_dataset(in_dir, out_file)
