import os
import re
import json
import argparse
from pathlib import Path

import pandas as pd

def try_parse(x):
    # Parse JSON-like strings or short delimited lists
    if x is None:
        return None
    if isinstance(x, (dict, list)):
        return x
    s = str(x).strip()
    if s == "" or s.lower() in ("nan", "none", "null"):
        return None
    if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
        try:
            return json.loads(s)
        except Exception:
            pass
    if len(s) < 300 and ("," in s or ";" in s):
        parts = re.split(r'\\s*[,;]\\s*', s)
        parts = [p for p in parts if p != ""]
        if len(parts) > 1:
            return parts
    return s

def flatten_dict(d, parent_key=""):
    out = {}
    if not isinstance(d, dict):
        return out
    for k, v in d.items():
        if parent_key == "":
            key = f"{k}"
        else:
            key = f"{parent_key}__{k}"
        if isinstance(v, dict):
            # Treat small dicts with 'value' as value holders and capture _src if present
            if "value" in v and len(v) <= 8:
                out[key] = v.get("value")
                if "_src" in v:
                    out[f"{key}__src"] = json.dumps(v["_src"], ensure_ascii=False)
            else:
                nested = flatten_dict(v, key)
                out.update(nested)
        else:
            out[key] = v
    return out

def coerce_numeric(val, field_name=""):
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    s = str(val).strip()
    if s == "" or s.lower() in ("nan", "none", "null"):
        return None
    s = s.replace(",", "")
    # percent
    if "%" in s:
        try:
            return float(s.replace("%", "").strip())
        except Exception:
            pass
    m = re.search(r"([-+]?\d*\\.?\\d+(?:[eE][-+]?\\d+)?)", s)
    if m:
        try:
            num = float(m.group(1))
        except Exception:
            return None
        lname = field_name.lower()
        if "qy" in lname or "quantum" in lname or "plqy" in lname:
            if abs(num) <= 1.0:
                return float(num * 100.0)
            return float(num)
        return float(num)
    return None

def detect_list_columns(df):
    cand = []
    for col in df.columns:
        sample = df[col].dropna().head(500)
        if any(isinstance(x, list) for x in sample):
            cand.append(col)
            continue
        sep_count = sum(1 for x in sample if isinstance(x, str) and (("," in x or ";" in x) and len(x) < 300))
        if sep_count > max(1, 0.01 * len(df)):
            cand.append(col)
    # avoid exploding very long-text columns
    cand = [c for c in cand if df[c].astype(str).map(len).median() < 300]
    for expected in ['ligands_smiles_list','ligand_classes','ligands','materials','targets','process']:
        if expected in df.columns and expected not in cand:
            cand.append(expected)
    return cand

def explode_and_flatten(input_csv, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    df_raw = pd.read_csv(input_csv, dtype=str, keep_default_na=False, na_values=[''])
    df = df_raw.copy()
    for col in df.columns:
        df[col] = df[col].apply(try_parse)
    list_cols = detect_list_columns(df)
    expanded = df.copy()
    for col in list_cols:
        def to_listcell(x):
            if isinstance(x, list):
                return x
            if isinstance(x, str) and ("," in x or ";" in x) and len(x) < 300:
                parts = re.split(r'\\s*[,;]\\s*', x)
                parts = [p for p in parts if p!='']
                return parts
            return [x] if x is not None else []
        expanded[col] = expanded[col].apply(to_listcell)
        expanded = expanded.explode(col, ignore_index=True)
    flattened_rows = []
    for _, row in expanded.iterrows():
        base = {}
        for col in expanded.columns:
            val = row[col]
            if isinstance(val, dict):
                flat = flatten_dict(val, parent_key=col)
                base.update(flat)
            else:
                base[col] = val
        flattened_rows.append(base)
    flat_df = pd.DataFrame(flattened_rows)
    # ensure __src columns are JSON strings
    for c in list(flat_df.columns):
        if c.endswith('__src'):
            flat_df[c] = flat_df[c].apply(lambda v: v if (isinstance(v, str) or v is None) else json.dumps(v, ensure_ascii=False))
    # make unique id
    def make_paper_id(row, idx):
        for key in ['doi','paper_title','paper_meta','source','paper.doi']:
            if key in row and row[key] not in (None, ''):
                s = str(row[key]).strip()
                return f"{s}__{idx}"
        return f"row__{idx}"
    ids = []
    for i, r in flat_df.iterrows():
        try:
            pid = make_paper_id(r, i)
        except Exception:
            pid = f"row__{i}"
        ids.append(f"{pid}__{i}")
    flat_df.insert(0, 'unique_id', ids)
    # coerce numeric columns
    for col in flat_df.columns:
        if col.endswith('__src') or col == 'unique_id':
            continue
        lname = col.lower()
        numeric_hint = any(k in lname for k in ['nm','ns','mv','pdi','qy','tau','lifetime','size','thickness','count','percent','brightness','sbr','photobleach','half','kalpha','kbeta','kgamma','t1','t2','t3','t4','t5'])
        if numeric_hint:
            flat_df[col] = flat_df[col].apply(lambda v: coerce_numeric(v, field_name=col) if v not in (None, '') else None)
        else:
            sample_vals = flat_df[col].dropna().astype(str).head(100)
            if len(sample_vals) > 0:
                numeric_count = sum(1 for v in sample_vals if re.search(r'^[-+]?\\d*\\.?\\d+(?:[eE][-+]?\\d+)?$', v))
                if numeric_count / len(sample_vals) > 0.6:
                    flat_df[col] = flat_df[col].apply(lambda v: coerce_numeric(v, field_name=col) if v not in (None, '') else None)
    out_path = os.path.join(out_dir, 'nfp_ml_expanded_flat.csv')
    flat_df.to_csv(out_path, index=False)
    return out_path

def encode_basic(tidy_csv, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    df = pd.read_csv(tidy_csv)
    cat_cols = [c for c in ['core_type','shell_type','localization','toxicity_class','solvent_system'] if c in df.columns]
    df_enc = pd.get_dummies(df, columns=cat_cols, dummy_na=True, dtype=int)
    if 'ligand_classes' in df.columns:
        all_vals = set()
        for v in df['ligand_classes'].fillna(''):
            for item in re.split(r'[;,]', str(v)):
                item = item.strip()
                if item:
                    all_vals.add(item)
        for cls in sorted(all_vals):
            df_enc[f'ligandcls__{cls}'] = df['ligand_classes'].fillna('').apply(lambda s: str(s).count(cls))
    if 'ligands_smiles_list' in df.columns:
        df_enc['ligand_count'] = df['ligands_smiles_list'].fillna('').apply(lambda s: len([x for x in str(s).strip('[]').split(',') if x.strip()!='']))
    enc_path = os.path.join(out_dir, 'nfp_ml_encoded.csv')
    df_enc.to_csv(enc_path, index=False)
    return enc_path

def main():
    parser = argparse.ArgumentParser(prog='prepare_ml_dataset', description='Prepare ML-ready datasets from nfp_samples.csv')
    parser.add_argument('--input_csv', type=str, default='../data/outputs/nfp_samples.csv', help='Path to nfp_samples.csv')
    parser.add_argument('--out_dir', type=str, default='../data/outputs/ml', help='Output directory')
    args = parser.parse_args()
    tidy = explode_and_flatten(args.input_csv, args.out_dir)
    enc = encode_basic(tidy, args.out_dir)
    print('Wrote:', tidy)
    print('Wrote:', enc)

if __name__ == '__main__':
    main()
