#!/usr/bin/env python3
"""
build_chiral_dataset.py - Build ML-ready dataset for chiral nanoprobe prediction
从提取的JSON文件构建手性纳米荧光探针机器学习数据集
"""

import os
import sys
import json
import glob
import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


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
    """Extract numeric range from string like '0.02 to 50.00 μM' or '1.5-2.0 nM'."""
    if not isinstance(value_str, str):
        return None, None, None
    
    s = value_str.strip()
    
    # Pattern: "number [- to ~] number unit"
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
    """Extract LOD numeric value and unit from string."""
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


def encode_chiral_type(chiral_type: Any) -> Dict[str, int]:
    """One-hot encode chiral type."""
    if chiral_type is None or not isinstance(chiral_type, str):
        return {
            'chiral_type_R': 0, 'chiral_type_S': 0,
            'chiral_type_D': 0, 'chiral_type_L': 0,
            'chiral_type_plus': 0, 'chiral_type_minus': 0,
            'chiral_type_racemic': 0
        }
    
    chiral_type = chiral_type.strip().upper()
    return {
        'chiral_type_R': 1 if chiral_type == 'R' else 0,
        'chiral_type_S': 1 if chiral_type == 'S' else 0,
        'chiral_type_D': 1 if chiral_type == 'D' else 0,
        'chiral_type_L': 1 if chiral_type == 'L' else 0,
        'chiral_type_plus': 1 if chiral_type in ('(+)', '+') else 0,
        'chiral_type_minus': 1 if chiral_type in ('(-)', '-') else 0,
        'chiral_type_racemic': 1 if chiral_type == 'RACEMIC' else 0
    }


def encode_analyte_category(category: Any) -> Dict[str, int]:
    """One-hot encode analyte category."""
    if category is None or not isinstance(category, str):
        return {
            'category_amino_acid': 0, 'category_drug': 0,
            'category_sugar': 0, 'category_metal_ion': 0,
            'category_protein': 0, 'category_nucleic_acid': 0,
            'category_other': 0
        }
    
    category = category.strip().lower()
    return {
        'category_amino_acid': 1 if 'amino' in category else 0,
        'category_drug': 1 if 'drug' in category else 0,
        'category_sugar': 1 if 'sugar' in category else 0,
        'category_metal_ion': 1 if 'metal' in category or 'ion' in category else 0,
        'category_protein': 1 if 'protein' in category else 0,
        'category_nucleic_acid': 1 if 'nucleic' in category or 'dna' in category or 'rna' in category else 0,
        'category_other': 1 if category not in ('amino_acid', 'drug', 'sugar', 'metal_ion', 'protein', 'nucleic_acid') else 0
    }


def encode_response_type(response_type: Any) -> Dict[str, int]:
    """One-hot encode response type."""
    if response_type is None or not isinstance(response_type, str):
        return {
            'response_turn_on': 0, 'response_turn_off': 0,
            'response_ratiometric': 0, 'response_colorimetric': 0,
            'response_cpl_on': 0, 'response_cpl_off': 0
        }
    
    response_type = response_type.strip().lower()
    return {
        'response_turn_on': 1 if 'turn-on' in response_type or 'turn on' in response_type else 0,
        'response_turn_off': 1 if 'turn-off' in response_type or 'turn off' in response_type else 0,
        'response_ratiometric': 1 if 'ratiometric' in response_type else 0,
        'response_colorimetric': 1 if 'colorimetric' in response_type else 0,
        'response_cpl_on': 1 if 'cpl_on' in response_type or 'cpl on' in response_type else 0,
        'response_cpl_off': 1 if 'cpl_off' in response_type or 'cpl off' in response_type else 0
    }


def extract_core_material_type(material: Any) -> str:
    """Categorize core material into broad types."""
    if material is None or not isinstance(material, str):
        return "unknown"
    
    material_lower = material.lower()
    
    if 'quantum dot' in material_lower or 'qd' in material_lower or 'qds' in material_lower:
        return "quantum_dot"
    elif 'carbon' in material_lower and ('dot' in material_lower or 'cd' in material_lower):
        return "carbon_dot"
    elif 'gold' in material_lower or 'au' in material_lower:
        return "gold"
    elif 'silver' in material_lower or 'ag' in material_lower:
        return "silver"
    elif 'silica' in material_lower or 'sio2' in material_lower:
        return "silica"
    elif 'polymer' in material_lower or 'pdot' in material_lower:
        return "polymer"
    elif 'upconversion' in material_lower or 'ucnp' in material_lower or 'nayf4' in material_lower:
        return "upconversion"
    elif 'mof' in material_lower:
        return "mof"
    elif 'nanotube' in material_lower or 'cnt' in material_lower or 'swcnt' in material_lower:
        return "nanotube"
    else:
        return "other"


def build_chiral_dataset(json_dir: str = 'outputs/chiral_extraction', 
                         out_path: str = 'outputs/chiral_nanoprobes_ml_dataset.csv'):
    """Build ML-ready dataset from extracted chiral nanoprobe JSON files."""
    logger.info("Building chiral nanoprobe ML dataset from %s...", json_dir)
    json_files = glob.glob(os.path.join(json_dir, "*.json"))
    
    if not json_files:
        logger.warning("No JSON files found.")
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
                
                # Clean numeric fields
                numeric_fields = [
                    'size_nm', 'excitation_wavelength_nm', 'emission_wavelength_nm',
                    'stokes_shift_nm', 'quantum_yield_percent', 'fluorescence_lifetime_ns',
                    'enantioselectivity_factor', 'glum_value', 'cpl_wavelength_nm',
                    'ph_value', 'temperature_celsius', 'chiral_center_count'
                ]
                for nf in numeric_fields:
                    if nf in flat:
                        flat[nf] = clean_numeric_field(flat[nf])
                
                # Extract LOD value
                if 'limit_of_detection' in flat and isinstance(flat['limit_of_detection'], str):
                    lod_val, lod_unit = extract_lod_value(flat['limit_of_detection'])
                    flat['lod_value'] = lod_val
                    flat['lod_unit'] = lod_unit
                
                # Extract linear range
                if 'linear_range' in flat and isinstance(flat['linear_range'], str):
                    low, high, unit = extract_numeric_range(flat['linear_range'])
                    if low is not None:
                        flat['linear_range_low'] = low
                        flat['linear_range_high'] = high
                        flat['linear_range_unit'] = unit
                
                # One-hot encode categorical fields
                flat.update(encode_chiral_type(flat.get('chiral_type')))
                flat.update(encode_analyte_category(flat.get('analyte_category')))
                flat.update(encode_response_type(flat.get('response_type')))
                
                # Categorize core material
                flat['core_material_type'] = extract_core_material_type(flat.get('core_material'))
                
                flat['_source_file'] = os.path.basename(jf)
                rows.append(flat)
        except json.JSONDecodeError as e:
            logger.error("Error parsing %s: %s", jf, e)
        except IOError as e:
            logger.error("Error reading %s: %s", jf, e)
            
    if not rows:
        logger.warning("No data to process.")
        return
        
    df = pd.DataFrame(rows)
    
    # Define mandatory fields for chiral nanoprobes
    mandatory = [
        'core_material',
        'chiral_source',
        'emission_wavelength_nm',
        'target_analyte'
    ]
    
    # Find and filter by mandatory fields
    filter_cols = []
    for m in mandatory:
        match_cols = [c for c in df.columns if m.lower() in c.lower()]
        if not match_cols:
            filter_cols.append(m)
            df[m] = np.nan
        else:
            best_col = sorted(match_cols, key=lambda c: df[c].notna().sum(), reverse=True)[0]
            filter_cols.append(best_col)
            
    before_count = len(df)
    for m in filter_cols:
        df = df[df[m].notna() & (df[m].astype(str).str.strip() != "")]
        
    logger.info("Filtering: Removed %d records missing mandatory fields.", before_count - len(df))
    
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
        logger.error("Error creating output directory: %s", e)
        return
    
    try:
        df.to_csv(out_path, index=False, encoding='utf-8-sig')
        logger.info("Saved chiral nanoprobe ML dataset with %d records to %s", len(df), out_path)
        
        # Also save feature summary
        summary_path = out_path.replace('.csv', '_summary.txt')
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write("Chiral Nanoprobe Dataset Summary\n")
            f.write("="*50 + "\n\n")
            f.write(f"Total records: {len(df)}\n")
            f.write(f"Total features: {len(df.columns)}\n\n")
            
            f.write("Mandatory fields:\n")
            for m in mandatory:
                f.write(f"  - {m}\n")
            
            f.write("\nChiral type distribution:\n")
            for col in ['chiral_type_R', 'chiral_type_S', 'chiral_type_D', 'chiral_type_L', 
                       'chiral_type_plus', 'chiral_type_minus', 'chiral_type_racemic']:
                if col in df.columns:
                    count = df[col].sum()
                    f.write(f"  - {col}: {count}\n")
            
            f.write("\nCore material types:\n")
            if 'core_material_type' in df.columns:
                for mat_type, count in df['core_material_type'].value_counts().items():
                    f.write(f"  - {mat_type}: {count}\n")
            
            f.write("\nAnalyte categories:\n")
            for col in ['category_amino_acid', 'category_drug', 'category_sugar', 
                       'category_metal_ion', 'category_protein']:
                if col in df.columns:
                    count = df[col].sum()
                    f.write(f"  - {col}: {count}\n")
            
            f.write("\nNumeric field statistics:\n")
            numeric_cols = ['size_nm', 'excitation_wavelength_nm', 'emission_wavelength_nm',
                          'quantum_yield_percent', 'enantioselectivity_factor', 'glum_value']
            for col in numeric_cols:
                if col in df.columns and df[col].notna().sum() > 0:
                    f.write(f"\n  {col}:\n")
                    f.write(f"    Mean: {df[col].mean():.2f}\n")
                    f.write(f"    Std: {df[col].std():.2f}\n")
                    f.write(f"    Min: {df[col].min():.2f}\n")
                    f.write(f"    Max: {df[col].max():.2f}\n")
                    f.write(f"    Non-null: {df[col].notna().sum()}\n")
        
        logger.info("Saved feature summary to %s", summary_path)
        
    except IOError as e:
        logger.error("Error saving dataset: %s", e)


if __name__ == '__main__':
    # 创建logs目录（在项目根目录下）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)  # 向上一级到项目根目录
    log_dir = os.path.join(project_root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # 生成带有时间戳的日志文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"dataset_build_{timestamp}.log")
    
    # 配置日志处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    
    # 配置根日志器
    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler, console_handler]
    )
    
    logger.info("=" * 60)
    logger.info("Starting chiral nanoprobe dataset building")
    logger.info("Log file: %s", log_file)
    logger.info("=" * 60)
    
    in_dir = sys.argv[1] if len(sys.argv) > 1 else 'outputs/chiral_extraction'
    out_file = sys.argv[2] if len(sys.argv) > 2 else 'outputs/chiral_nanoprobes_ml_dataset.csv'
    build_chiral_dataset(in_dir, out_file)
    
    logger.info("=" * 60)
    logger.info("Dataset building completed")
    logger.info("Log saved to: %s", log_file)
    logger.info("=" * 60)