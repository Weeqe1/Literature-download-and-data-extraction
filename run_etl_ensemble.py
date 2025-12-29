#!/usr/bin/env python3
# run_etl_ensemble.py - Multi-model PDF information extraction driver
"""
Multi-model ensemble extraction pipeline:
1. Parse PDF to extract text content
2. Build prompt with PDF content and schema
3. Call multiple LLMs to extract structured data
4. Compare outputs and reach consensus
5. Re-extract if disagreements exist
6. Save results or flag for human review
"""
import os
import argparse
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

from etl_ensemble.pdf_parser import parse_pdf, truncate_text
from etl_ensemble.llm_multi_client import MultiModelClient
from etl_ensemble.consensus_engine import compare_outputs
from etl_ensemble.focused_reextractor import reextract
from etl_ensemble.human_review_manager import save_review_case


def load_config(cfg_path: str) -> Dict[str, Any]:
    """Load YAML configuration file."""
    with open(cfg_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_schema(schema_path: str) -> Dict[str, Any]:
    """Load extraction schema and convert to JSON Schema format."""
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_yml = yaml.safe_load(f)
    
    # Convert to simplified JSON Schema for LLM
    properties = {}
    for section_name, fields in schema_yml.items():
        if section_name == 'version':
            continue
        if isinstance(fields, list):
            for field in fields:
                name = field.get('name')
                ftype = field.get('type', 'str')
                if ftype in ('str', 'string'):
                    properties[name] = {"type": "string"}
                elif ftype in ('int', 'integer'):
                    properties[name] = {"type": "integer"}
                elif ftype in ('float', 'number'):
                    properties[name] = {"type": "number"}
                elif ftype == 'bool':
                    properties[name] = {"type": "boolean"}
                elif ftype == 'enum':
                    properties[name] = {"type": "string", "enum": field.get('enum', [])}
                elif ftype in ('list_str', 'list'):
                    properties[name] = {"type": "array", "items": {"type": "string"}}
                elif ftype == 'dict':
                    properties[name] = {"type": "object"}
                else:
                    properties[name] = {"type": "string"}
    
    return {
        "type": "object",
        "properties": properties,
        "additionalProperties": True
    }


def build_extraction_prompt(prompt_template: str, pdf_text: str, max_text_length: int = 40000) -> str:
    """Build the full extraction prompt with PDF content."""
    # Truncate text if too long
    truncated_text = truncate_text(pdf_text, max_text_length)
    
    full_prompt = f"""{prompt_template}

---

## Paper Content

{truncated_text}
"""
    return full_prompt


def run_one_pdf(pdf_path: str, cfg: Dict[str, Any], prompt_template: str, 
                schema: Dict[str, Any], output_dir: str, verbose: bool = True) -> Dict[str, Any]:
    """Process a single PDF file through the multi-model extraction pipeline."""
    
    if verbose:
        print(f"  [1/5] Parsing PDF...")
    
    # Step 1: Parse PDF
    pdf_data = parse_pdf(pdf_path)
    if "error" in pdf_data:
        return {"status": "error", "message": pdf_data["error"]}
    
    pdf_text = pdf_data.get("text", "")
    if not pdf_text.strip():
        return {"status": "error", "message": "No text extracted from PDF"}
    
    if verbose:
        print(f"        Extracted {len(pdf_text)} chars from {pdf_data['metadata'].get('page_count', 0)} pages")
    
    # Step 2: Build prompt with PDF content
    full_prompt = build_extraction_prompt(prompt_template, pdf_text)
    
    if verbose:
        print(f"  [2/5] Calling multiple models...")
    
    # Step 3: Call all configured models
    mmc = MultiModelClient(cfg)
    model_ids = [m['id'] for m in cfg.get('models', [])]
    
    if not model_ids:
        return {"status": "error", "message": "No models configured in llm_backends.yml"}
    
    results = []
    for mid in model_ids:
        if verbose:
            print(f"        Calling {mid}...")
        try:
            out = mmc.extract(mid, full_prompt, schema=schema)
            results.append(out)
        except Exception as e:
            if verbose:
                print(f"        {mid} failed: {e}")
            results.append({"model_id": mid, "resp": {"error": str(e)}})
    
    if verbose:
        print(f"  [3/5] Comparing model outputs...")
    
    # Step 4: Compare outputs
    thresholds = cfg.get('thresholds', {})
    comp = compare_outputs(results, thresholds=thresholds)
    
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # If all agree, save result
    if not comp.get('disagreed'):
        if verbose:
            print(f"  [4/5] All models agree!")
        rec = {k: v['value'] for k, v in comp.get('agreed', {}).items()}
        rec['_models'] = model_ids
        rec['_source_pdf'] = pdf_path
        
        fn = out_dir / (Path(pdf_path).stem + '.json')
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump({
                'pdf': pdf_path,
                'record': rec,
                'meta': {
                    'agreed_fields': list(comp.get('agreed', {}).keys()),
                    'model_ids': model_ids
                }
            }, f, ensure_ascii=False, indent=2)
        
        if verbose:
            print(f"  [5/5] Saved to {fn}")
        return {'status': 'ok', 'saved': str(fn), 'agreed_fields': len(comp.get('agreed', {}))}
    
    # Step 5: Re-extract focusing on disagreements
    if verbose:
        disagreed_fields = list(comp.get('disagreed', {}).keys())
        print(f"  [4/5] Disagreements on {len(disagreed_fields)} fields: {disagreed_fields[:5]}...")
        print(f"        Performing focused re-extraction...")
    
    re_results = reextract(mmc, model_ids, full_prompt, comp.get('disagreed'), snippets=None)
    comp2 = compare_outputs(re_results, thresholds=thresholds)
    
    if not comp2.get('disagreed'):
        if verbose:
            print(f"        Re-extraction resolved all disagreements!")
        rec = {k: v['value'] for k, v in comp2.get('agreed', {}).items()}
        rec['_models'] = model_ids
        rec['_source_pdf'] = pdf_path
        
        fn = out_dir / (Path(pdf_path).stem + '.json')
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump({
                'pdf': pdf_path,
                'record': rec,
                'meta': {
                    'agreed_fields': list(comp2.get('agreed', {}).keys()),
                    'model_ids': model_ids,
                    'required_reextraction': True
                }
            }, f, ensure_ascii=False, indent=2)
        
        if verbose:
            print(f"  [5/5] Saved to {fn}")
        return {'status': 'ok_after_reextract', 'saved': str(fn)}
    
    # Still disagrees - save for human review
    if verbose:
        remaining = list(comp2.get('disagreed', {}).keys())
        print(f"        Still disagree on {len(remaining)} fields. Saving for review.")
    
    review_fn = save_review_case(str(out_dir), pdf_path, comp2)
    
    if verbose:
        print(f"  [5/5] Saved for review: {review_fn}")
    
    return {
        'status': 'review',
        'review_file': review_fn,
        'disagreed_fields': list(comp2.get('disagreed', {}).keys())
    }


def main():
    parser = argparse.ArgumentParser(description='Multi-model PDF information extraction')
    parser.add_argument('--pdf_dir', default='data/pdfs', help='Directory containing PDF files')
    parser.add_argument('--cfg', default='configs/extraction/llm_backends.yml', help='LLM backends config')
    parser.add_argument('--schema', default='configs/extraction/schema.yml', help='Extraction schema')
    parser.add_argument('--out_dir', default='data/outputs/extraction', help='Output directory')
    parser.add_argument('--prompt_file', default='configs/extraction/prompts/paper_summarize.md', help='Prompt template')
    parser.add_argument('--verbose', action='store_true', default=True, help='Verbose output')
    args = parser.parse_args()
    
    # Load configurations
    print("Loading configurations...")
    cfg = load_config(args.cfg)
    schema = load_schema(args.schema)
    
    # Load prompt template
    prompt_template = 'Extract structured information from the paper and return as JSON.'
    if os.path.exists(args.prompt_file):
        with open(args.prompt_file, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
        print(f"Loaded prompt from {args.prompt_file}")
    else:
        print(f"Warning: Prompt file not found, using default prompt")
    
    # Find PDFs
    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.exists():
        print(f"Error: PDF directory not found: {pdf_dir}")
        return
    
    pdfs = list(pdf_dir.glob('*.pdf'))
    print(f"Found {len(pdfs)} PDF files in {pdf_dir}")
    
    if not pdfs:
        print("No PDF files to process.")
        return
    
    # Process each PDF
    results_summary = {'ok': 0, 'ok_after_reextract': 0, 'review': 0, 'error': 0}
    
    for i, pdf_path in enumerate(pdfs, 1):
        print(f"\n[{i}/{len(pdfs)}] Processing: {pdf_path.name}")
        try:
            result = run_one_pdf(str(pdf_path), cfg, prompt_template, schema, args.out_dir, verbose=args.verbose)
            status = result.get('status', 'error')
            results_summary[status] = results_summary.get(status, 0) + 1
            print(f"  Result: {status}")
        except Exception as e:
            print(f"  Error: {e}")
            results_summary['error'] += 1
    
    # Summary
    print("\n" + "="*50)
    print("Processing Complete!")
    print(f"  OK (direct):      {results_summary['ok']}")
    print(f"  OK (reextracted): {results_summary['ok_after_reextract']}")
    print(f"  Needs review:     {results_summary['review']}")
    print(f"  Errors:           {results_summary['error']}")
    print("="*50)


if __name__ == '__main__':
    main()
