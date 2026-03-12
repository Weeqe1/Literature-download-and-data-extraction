import os
import sys
import json
import glob
import pandas as pd
import numpy as np

def flatten_dict(d, parent_key=""):
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

def build_dataset(json_dir='outputs/extraction', out_path='outputs/nfp_ml_ready_dataset.csv'):
    print(f"\n[Post-Processing] Building ML-ready dataset from {json_dir}...")
    json_files = glob.glob(os.path.join(json_dir, "*.json"))
    
    rows = []
    for jf in json_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            paper_meta = data.get("paper_metadata", {})
            samples = data.get("samples", [])
            
            for s in samples:
                # Merge sample data and paper metadata
                merged = s.copy()
                for k, v in paper_meta.items():
                    merged[f"paper_{k}"] = v
                
                flat = flatten_dict(merged)
                flat['_source_file'] = os.path.basename(jf)
                rows.append(flat)
        except Exception as e:
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
    
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            pass
        else:
            df[col] = df[col].fillna("Not Specified")
            df[col] = df[col].replace(r'^\s*$', "Not Specified", regex=True)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"  Success: Saved ML-ready dataset with {len(df)} records to {out_path}")

if __name__ == '__main__':
    in_dir = sys.argv[1] if len(sys.argv) > 1 else 'outputs/extraction'
    out_file = sys.argv[2] if len(sys.argv) > 2 else 'outputs/nfp_ml_ready_dataset.csv'
    build_dataset(in_dir, out_file)
