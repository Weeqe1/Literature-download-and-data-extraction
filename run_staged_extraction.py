#!/usr/bin/env python3
# run_staged_extraction.py - Multi-stage PDF information extraction
"""
分阶段提取流水线：
将字段拆分为多个阶段，每阶段聚焦相关字段。
各阶段提取结果合并为最终 JSON 输出。
"""
import os
import sys
import argparse
import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
import concurrent.futures

# Fix Windows console encoding issues
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from etl_ensemble.pdf_parser import parse_pdf, truncate_text, extract_images_from_pdf
from etl_ensemble.llm_multi_client import MultiModelClient


# 定义提取阶段（Stage 2 为多模态图片分析）
STAGES = [
    {"id": 1, "name": "core_extraction", "file": "stage1_core_extraction.md", "desc": "Core 12-Field Extraction", "multimodal": False},
    {"id": 2, "name": "figure_analysis", "file": "stage2_figure_analysis.md", "desc": "Multimodal Figure Analysis", "multimodal": True}
]


def load_schema_from_yaml(schema_path: str) -> Dict[str, Any]:
    """Load schema definition from schema.yml file.
    
    Returns:
        Dict with 'paper_meta' and 'probe_features' field definitions
    """
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = yaml.safe_load(f)
    
    return schema


def get_schema_field_names(schema: Dict[str, Any]) -> List[str]:
    """Extract all field names from schema definition.
    
    Args:
        schema: Loaded schema dict with 'paper_meta' and 'probe_features' keys
        
    Returns:
        List of field names (e.g., ['title', 'doi', 'year', 'core_material', ...])
    """
    fields = []
    
    # Paper metadata fields
    for field_def in schema.get('paper_meta', []):
        if isinstance(field_def, dict) and 'name' in field_def:
            fields.append(field_def['name'])
    
    # Probe feature fields
    for field_def in schema.get('probe_features', []):
        if isinstance(field_def, dict) and 'name' in field_def:
            fields.append(field_def['name'])
    
    return fields


def fill_missing_fields(sample: Dict[str, Any], schema_fields: List[str]) -> Dict[str, Any]:
    """Ensure all schema fields are present in sample, filling missing with null.
    
    Args:
        sample: Extracted sample dict
        schema_fields: List of field names from schema.yml
        
    Returns:
        Sample dict with all schema fields present
    """
    filled = {}
    for field in schema_fields:
        filled[field] = sample.get(field, None)
    # Add any extra fields that were extracted but not in schema (e.g., metadata)
    for key, value in sample.items():
        if key not in filled:
            filled[key] = value
    return filled


def load_config(cfg_path: str) -> Dict[str, Any]:
    """Load YAML configuration file."""
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"[Error] Invalid YAML in {cfg_path}: {e}")
        return {}
    except IOError as e:
        print(f"[Error] Cannot read {cfg_path}: {e}")
        return {}


def load_stage_prompt(stages_dir: str, stage_file: str) -> str:
    """Load prompt template for a specific stage."""
    prompt_path = Path(stages_dir) / stage_file
    if not prompt_path.exists():
        raise FileNotFoundError(f"Stage prompt not found: {prompt_path}")
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()


def build_stage_prompt(stage_prompt: str, pdf_text: str, max_text_length: int = 30000) -> str:
    """Build the full extraction prompt with PDF content."""
    # Truncate text if too long
    if len(pdf_text) > max_text_length:
        half = max_text_length // 2
        truncated_text = pdf_text[:half] + "\n\n...[TRUNCATED]...\n\n" + pdf_text[-half:]
    else:
        truncated_text = pdf_text
    
    return f"""{stage_prompt}

---

## Paper Content

{truncated_text}
"""


def run_single_stage(
    mmc: MultiModelClient,
    model_id: str,
    stage_prompt: str,
    pdf_text: str,
    stage_name: str,
    images: Optional[List[Dict[str, Any]]] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """Run a single extraction stage.
    
    Args:
        mmc: Multi-model client
        model_id: Model ID to use
        stage_prompt: Prompt template for this stage
        pdf_text: Extracted text from PDF
        stage_name: Name of this stage
        images: List of image dicts with 'base64' and 'mime_type' keys (for multimodal stages)
        verbose: Print progress
    """
    full_prompt = build_stage_prompt(stage_prompt, pdf_text)
    
    # Convert images to data URLs for multimodal LLM
    image_urls = None
    if images:
        image_urls = []
        for img in images:
            data_url = f"data:{img['mime_type']};base64,{img['base64']}"
            image_urls.append(data_url)
    
    try:
        out = mmc.extract(model_id, full_prompt, schema={"type": "object"}, images=image_urls)
        resp = out.get('resp', {})
        
        # Check for errors
        if isinstance(resp, dict) and resp.get('error'):
            raise RuntimeError(f"Model error: {resp['error']}")
        
        return resp
    except RuntimeError:
        raise
    except ValueError as e:
        if verbose:
            print(f"      Stage {stage_name} value error: {e}")
        raise
    except KeyError as e:
        if verbose:
            print(f"      Stage {stage_name} missing key: {e}")
        raise
    except Exception as e:
        error_str = str(e).lower()
        # Detect if error is related to image/multimodal not supported
        if images and any(kw in error_str for kw in ['image', 'multimodal', 'vision', 'unsupported', 'content_type']):
            if verbose:
                print(f"      ⚠️ Stage {stage_name} failed: Model may not support image input.")
                print(f"         Consider using a multimodal model (GPT-4o, GPT-4V, Gemini 1.5 Pro) for Stage 2.")
        elif verbose:
            print(f"      Stage {stage_name} failed: {e}")
        raise


def merge_samples_by_id(all_stage_samples: Dict[str, List[Dict]], model_ids: List[str]) -> List[Dict[str, Any]]:
    """Merge samples from different stages by sample_id, respecting model priority.
    
    Args:
        all_stage_samples: Dict mapping stage_name -> list of sample dicts
        model_ids: List of model IDs in priority order (0 = highest)
        
    Returns:
        List of merged sample dicts
    """
    merged = {}  # sample_id -> merged dict
    priority_map = {m_id: i for i, m_id in enumerate(model_ids)}
    field_priority = {}  # sample_id -> {field: priority}
    
    for stage_name, samples in all_stage_samples.items():
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            sample_id = sample.get('sample_id', 'default')
            model_id = sample.get('_extracted_by', 'unknown')
            curr_prio = priority_map.get(model_id, 999)
            
            if sample_id not in merged:
                merged[sample_id] = {'sample_id': sample_id}
                field_priority[sample_id] = {}
                
            # Merge fields based on model priority (lower number = better)
            for k, v in sample.items():
                if v is None:
                    continue
                exist_prio = field_priority[sample_id].get(k, 999)
                if curr_prio <= exist_prio:
                    merged[sample_id][k] = v
                    field_priority[sample_id][k] = curr_prio
    
    return list(merged.values())


def run_staged_extraction(
    pdf_path: str,
    cfg: Dict[str, Any],
    stages_dir: str,
    output_dir: str,
    schema_path: str,
    stages_to_run: Optional[List[int]] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """Run multi-stage extraction on a single PDF with multi-sample support."""
    
    # Load schema from YAML
    try:
        schema = load_schema_from_yaml(schema_path)
        schema_fields = get_schema_field_names(schema)
        if verbose:
            print(f"        Loaded {len(schema_fields)} fields from schema.yml")
    except (FileNotFoundError, yaml.YAMLError) as e:
        return {"status": "error", "message": f"Schema load error: {e}"}
    
    # Step 1: Parse PDF
    if verbose:
        print(f"  [1/4] Parsing PDF...")
    
    pdf_data = parse_pdf(pdf_path)
    if "error" in pdf_data:
        return {"status": "error", "message": pdf_data["error"]}
    
    pdf_text = pdf_data.get("text", "")
    if not pdf_text.strip():
        return {"status": "error", "message": "No text extracted from PDF"}
    
    if verbose:
        print(f"        Extracted {len(pdf_text)} chars from {pdf_data['metadata'].get('page_count', 0)} pages")
    
    # Step 1b: Extract images for multimodal stages
    pdf_images = []
    if any(stage["id"] in stages_to_run for stage in STAGES if stage.get("multimodal")):
        if verbose:
            print(f"  [1b/4] Extracting images for multimodal analysis...")
        pdf_images = extract_images_from_pdf(pdf_path, max_images=8)
        if verbose:
            print(f"        Found {len(pdf_images)} images")
    
    # Step 2: Get enabled models
    enabled_models = [m for m in cfg.get('models', []) if m.get('enabled', True)]
    if not enabled_models:
        return {"status": "error", "message": "No enabled models in llm_backends.yml"}
    
    model_ids = [m['id'] for m in enabled_models]
    mmc = MultiModelClient(cfg)
    
    if verbose:
        print(f"  [2/4] Running staged extraction with {len(model_ids)} model(s): {', '.join(model_ids)}")
    
    # Step 3: Run each stage with ALL models and collect samples
    stages_to_process = stages_to_run or [1]
    all_stage_samples = {}  # stage_name -> list of samples (merged from all models)
    paper_metadata = {}  # Stage 1 metadata (shared across samples)
    stage_results = {}
    total_stages = len([s for s in STAGES if s["id"] in stages_to_process])
    current_stage_num = 0
    
    for stage in STAGES:
        if stage["id"] not in stages_to_process:
            continue
        
        current_stage_num += 1
        if verbose:
            print(f"        Stage {current_stage_num}/{total_stages}: {stage['desc']}...")
        
        stage_prompt = load_stage_prompt(stages_dir, stage["file"])
        stage_images = pdf_images if stage.get("multimodal") else None
        
        # Collect results from ALL models concurrently for this stage
        if verbose:
            print(f"          -> Concurrently calling {len(model_ids)} models...")
            
        model_results_raw = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(model_ids), 10)) as executor:
            future_to_model = {
                executor.submit(run_single_stage, mmc, m_id, stage_prompt, pdf_text, stage["name"], stage_images, False): m_id
                for m_id in model_ids
            }
            for future in concurrent.futures.as_completed(future_to_model):
                m_id = future_to_model[future]
                try:
                    result = future.result()
                    if result:
                        model_results_raw.append({"model_id": m_id, "result": result})
                        if verbose:
                            print(f"          -> {m_id} completed successfully")
                except Exception as e:
                    if verbose:
                        print(f"          -> {m_id} failed: {e}")
        
        # Sort model_results by original priority (model_ids order)
        model_results = sorted(model_results_raw, key=lambda x: model_ids.index(x["model_id"]))
        
        # Merge results from all models
        if model_results:
            if stage["id"] == 1:
                # Stage 1 (metadata) - use first successful result
                paper_metadata = model_results[0]["result"]
                stage_results[stage["name"]] = {"models_used": [r["model_id"] for r in model_results]}
                if verbose:
                    print(f"          -> Metadata from {model_results[0]['model_id']}")
            else:
                # Stages 2-7: merge samples from all models
                merged_stage_samples = []
                for mr in model_results:
                    samples = mr["result"].get('samples', [])
                    if not samples and mr["result"]:
                        samples = [mr["result"]]
                    for s in samples:
                        if isinstance(s, dict):
                            s['_extracted_by'] = mr["model_id"]
                            merged_stage_samples.append(s)
                
                all_stage_samples[stage["name"]] = merged_stage_samples
                stage_results[stage["name"]] = {
                    "models_used": [r["model_id"] for r in model_results],
                    "total_samples": len(merged_stage_samples)
                }
                if verbose:
                    print(f"          -> {len(merged_stage_samples)} sample(s) from {len(model_results)} model(s)")
    
    # Step 4: Merge samples by sample_id
    if verbose:
        print(f"  [3/4] Merging samples by sample_id (priority-based)...")
    
    merged_samples = merge_samples_by_id(all_stage_samples, model_ids)
    
    # Add paper metadata to each sample and fill missing fields with null
    filled_samples = []
    for sample in merged_samples:
        sample.update({f"paper_{k}": v for k, v in paper_metadata.items() if k != 'sample_count'})
        sample['_source_pdf'] = pdf_path
        sample['_models_used'] = model_ids
        # Fill all missing schema fields with null
        filled_sample = fill_missing_fields(sample, schema_fields)
        filled_samples.append(filled_sample)
    
    if verbose:
        print(f"  [4/4] Saving results...")
    
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Count total non-null fields across all samples
    total_fields = sum(
        sum(1 for k, v in sample.items() if not k.startswith('_') and not k.startswith('paper_') and v is not None)
        for sample in filled_samples
    )
    
    output = {
        'pdf': pdf_path,
        'paper_metadata': paper_metadata,
        'samples': filled_samples,
        'meta': {
            'models_used': model_ids,
            'stages': list(stage_results.keys()),
            'stage_details': stage_results,
            'sample_count': len(filled_samples),
            'total_fields_extracted': total_fields
        }
    }
    
    fn = out_dir / (Path(pdf_path).stem + '.json')
    with open(fn, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    if verbose:
        print(f"        Saved to {fn} ({len(merged_samples)} samples, {total_fields} fields)")
    
    return {
        'status': 'ok',
        'saved': str(fn),
        'sample_count': len(merged_samples),
        'total_fields': total_fields,
        'stages_completed': len(stage_results)
    }


def main():
    parser = argparse.ArgumentParser(description='Multi-stage PDF information extraction')
    parser.add_argument('--pdf_dir', default='outputs/literature/PDF', help='Directory containing PDF files')
    parser.add_argument('--cfg', default='configs/extraction/llm_backends.yml', help='LLM backends config')
    parser.add_argument('--schema', default='configs/extraction/schema.yml', help='Schema definition file')
    parser.add_argument('--stages_dir', default='configs/extraction/stages', help='Directory containing stage prompts')
    parser.add_argument('--out_dir', default='outputs/extraction', help='Output directory')
    parser.add_argument('--stages', type=str, default='1,2', help='Comma-separated stage numbers to run (e.g., "1,2")')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of PDFs to process (0 = no limit)')
    parser.add_argument('--verbose', action='store_true', default=True, help='Verbose output')
    args = parser.parse_args()
    
    # Parse stages
    stages_to_run = [int(s.strip()) for s in args.stages.split(',')]
    
    # Load config
    print("Loading configurations...")
    cfg = load_config(args.cfg)
    
    # Find PDFs
    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.exists():
        print(f"Error: PDF directory not found: {pdf_dir}")
        return
    
    pdfs = list(pdf_dir.glob('*.pdf'))
    if args.limit > 0:
        pdfs = pdfs[:args.limit]
    
    print(f"Found {len(pdfs)} PDF files in {pdf_dir}")
    print(f"Running stages: {stages_to_run}")
    
    if not pdfs:
        print("No PDF files to process.")
        return
    
    # Process each PDF
    results_summary = {'ok': 0, 'error': 0, 'total_fields': 0}
    
    for i, pdf_path in enumerate(pdfs, 1):
        print(f"\n[{i}/{len(pdfs)}] Processing: {pdf_path.name}")
        try:
            result = run_staged_extraction(
                str(pdf_path), cfg, args.stages_dir, args.out_dir, args.schema,
                stages_to_run=stages_to_run, verbose=args.verbose
            )
            status = result.get('status', 'error')
            results_summary[status] = results_summary.get(status, 0) + 1
            results_summary['total_fields'] += result.get('total_fields', 0)
            print(f"  Result: {status}")
        except FileNotFoundError as e:
            print(f"  Error: File not found - {e}")
            results_summary['error'] += 1
        except yaml.YAMLError as e:
            print(f"  Error: Invalid YAML config - {e}")
            results_summary['error'] += 1
        except ValueError as e:
            print(f"  Error: Invalid value - {e}")
            results_summary['error'] += 1
        except Exception as e:
            print(f"  Error: {e}")
            results_summary['error'] += 1
    
    # Summary
    print("\n" + "="*50)
    print("Processing Complete!")
    print(f"  OK:           {results_summary['ok']}")
    print(f"  Errors:       {results_summary['error']}")
    print(f"  Total fields: {results_summary['total_fields']}")
    print("="*50)
    out_csv = os.path.join(os.path.dirname(args.out_dir) if args.out_dir.endswith('extraction') else args.out_dir, 'nfp_ml_ready_dataset.csv')
    try:
        build_clean_dataset.build_dataset(args.out_dir, out_csv)
    except Exception as e:
        print('Failed to build dataset:', e)


if __name__ == '__main__':
    main()
