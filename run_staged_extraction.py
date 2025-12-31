#!/usr/bin/env python3
# run_staged_extraction.py - Multi-stage PDF information extraction
"""
分阶段提取流水线：
将 90+ 字段拆分为 6 个阶段，每阶段聚焦 10-17 个相关字段。
各阶段提取结果合并为最终 JSON 输出。
"""
import os
import sys
import argparse
import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional

# Fix Windows console encoding issues
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from etl_ensemble.pdf_parser import parse_pdf, truncate_text, extract_images_from_pdf
from etl_ensemble.llm_multi_client import MultiModelClient


# 定义 7 个提取阶段（Stage 7 为多模态图片分析）
STAGES = [
    {"id": 1, "name": "metadata", "file": "stage1_metadata.md", "desc": "论文元数据", "multimodal": False},
    {"id": 2, "name": "material", "file": "stage2_material.md", "desc": "材料与结构", "multimodal": False},
    {"id": 3, "name": "synthesis", "file": "stage3_synthesis.md", "desc": "合成参数", "multimodal": False},
    {"id": 4, "name": "optical", "file": "stage4_optical.md", "desc": "光学性能", "multimodal": False},
    {"id": 5, "name": "surface", "file": "stage5_surface.md", "desc": "表面与稳定性", "multimodal": False},
    {"id": 6, "name": "bio", "file": "stage6_bio.md", "desc": "生物应用", "multimodal": False},
    {"id": 7, "name": "figures", "file": "stage7_figures.md", "desc": "图片分析", "multimodal": True},
]


def load_config(cfg_path: str) -> Dict[str, Any]:
    """Load YAML configuration file."""
    with open(cfg_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


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
    except Exception as e:
        error_str = str(e).lower()
        # Detect if error is related to image/multimodal not supported
        if images and any(kw in error_str for kw in ['image', 'multimodal', 'vision', 'unsupported', 'content_type']):
            if verbose:
                print(f"      ⚠️ Stage {stage_name} failed: Model may not support image input.")
                print(f"         Consider using a multimodal model (GPT-4o, GPT-4V, Gemini 1.5 Pro) for Stage 7.")
        elif verbose:
            print(f"      Stage {stage_name} failed: {e}")
        raise


def merge_samples_by_id(all_stage_samples: Dict[str, List[Dict]]) -> List[Dict[str, Any]]:
    """Merge samples from different stages by sample_id.
    
    Args:
        all_stage_samples: Dict mapping stage_name -> list of sample dicts
        
    Returns:
        List of merged sample dicts
    """
    merged = {}  # sample_id -> merged dict
    
    for stage_name, samples in all_stage_samples.items():
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            sample_id = sample.get('sample_id', 'default')
            if sample_id not in merged:
                merged[sample_id] = {'sample_id': sample_id}
            # Merge fields from this stage
            for k, v in sample.items():
                if v is not None and k not in merged[sample_id]:
                    merged[sample_id][k] = v
                elif v is not None and merged[sample_id].get(k) is None:
                    merged[sample_id][k] = v
    
    return list(merged.values())


def run_staged_extraction(
    pdf_path: str,
    cfg: Dict[str, Any],
    stages_dir: str,
    output_dir: str,
    stages_to_run: Optional[List[int]] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """Run multi-stage extraction on a single PDF with multi-sample support."""
    
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
    
    # Step 2: Get enabled model
    enabled_models = [m for m in cfg.get('models', []) if m.get('enabled', True)]
    if not enabled_models:
        return {"status": "error", "message": "No enabled models in llm_backends.yml"}
    
    model_id = enabled_models[0]['id']
    mmc = MultiModelClient(cfg)
    
    if verbose:
        print(f"  [2/4] Running staged extraction with {model_id}...")
    
    # Step 3: Run each stage and collect samples
    stages_to_process = stages_to_run or [1, 2, 3, 4, 5, 6, 7]  # Default: all 7 stages including image analysis
    all_stage_samples = {}  # stage_name -> list of samples
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
        
        try:
            stage_prompt = load_stage_prompt(stages_dir, stage["file"])
            
            # Pass images only for multimodal stages
            stage_images = pdf_images if stage.get("multimodal") else None
            result = run_single_stage(mmc, model_id, stage_prompt, pdf_text, stage["name"], images=stage_images, verbose=verbose)
            
            if isinstance(result, dict):
                # Stage 1 (metadata) is special - shared across all samples
                if stage["id"] == 1:
                    paper_metadata = {k: v for k, v in result.items() if v is not None}
                    stage_results[stage["name"]] = result
                    non_null = sum(1 for v in result.values() if v is not None)
                    if verbose:
                        print(f"          -> Extracted {non_null} metadata fields")
                else:
                    # Stages 2-6: expect {samples: [...]} format
                    samples = result.get('samples', [])
                    if not samples and result:
                        # Fallback: treat as single sample if no 'samples' key
                        samples = [result]
                    
                    all_stage_samples[stage["name"]] = samples
                    stage_results[stage["name"]] = {"sample_count": len(samples)}
                    
                    if verbose:
                        print(f"          -> Extracted {len(samples)} sample(s)")
            
        except Exception as e:
            if verbose:
                print(f"          -> Failed: {e}")
            stage_results[stage["name"]] = {"error": str(e)}
    
    # Step 4: Merge samples by sample_id
    if verbose:
        print(f"  [3/4] Merging samples by sample_id...")
    
    merged_samples = merge_samples_by_id(all_stage_samples)
    
    # Add paper metadata to each sample
    for sample in merged_samples:
        sample.update({f"paper_{k}": v for k, v in paper_metadata.items() if k != 'sample_count'})
        sample['_source_pdf'] = pdf_path
        sample['_model'] = model_id
    
    if verbose:
        print(f"  [4/4] Saving results...")
    
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Count total non-null fields across all samples
    total_fields = sum(
        sum(1 for k, v in sample.items() if not k.startswith('_') and v is not None)
        for sample in merged_samples
    )
    
    output = {
        'pdf': pdf_path,
        'paper_metadata': paper_metadata,
        'samples': merged_samples,
        'meta': {
            'model_id': model_id,
            'stages': list(stage_results.keys()),
            'sample_count': len(merged_samples),
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
    parser.add_argument('--stages_dir', default='configs/extraction/stages', help='Directory containing stage prompts')
    parser.add_argument('--out_dir', default='outputs/extraction', help='Output directory')
    parser.add_argument('--stages', type=str, default='1,2,3,4,5,6,7', help='Comma-separated stage numbers to run (e.g., "1,4" for metadata and optical only)')
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
                str(pdf_path), cfg, args.stages_dir, args.out_dir,
                stages_to_run=stages_to_run, verbose=args.verbose
            )
            status = result.get('status', 'error')
            results_summary[status] = results_summary.get(status, 0) + 1
            results_summary['total_fields'] += result.get('total_fields', 0)
            print(f"  Result: {status}")
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


if __name__ == '__main__':
    main()
