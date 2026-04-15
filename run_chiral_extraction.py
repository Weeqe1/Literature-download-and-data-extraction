#!/usr/bin/env python3
# run_chiral_extraction.py - Chiral Nano Fluorescent Probe Extraction
"""
手性纳米荧光探针信息提取流水线：
从PDF文献中提取手性纳米荧光探针的结构化数据
"""

import os
import sys
import argparse
import json
import logging
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
import concurrent.futures

# Fix Windows console encoding issues
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from etl_ensemble.pdf_parser import parse_pdf, truncate_text, extract_images_from_pdf
from etl_ensemble.llm_multi_client import MultiModelClient
import build_clean_dataset

logger = logging.getLogger(__name__)

# 定义提取阶段
STAGES = [
    {"id": 1, "name": "chiral_extraction", "file": "stage1_chiral_extraction.md", 
     "desc": "Chiral Nanoprobe Extraction", "multimodal": False},
]


def load_schema_from_yaml(schema_path: str) -> Dict[str, Any]:
    """Load schema definition from schema_chiral.yml file."""
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = yaml.safe_load(f)
    
    return schema


def get_schema_field_names(schema: Dict[str, Any]) -> List[str]:
    """Extract all field names from schema definition."""
    fields = []
    
    # 遍历所有schema部分
    for section_name, section_fields in schema.items():
        if isinstance(section_fields, list):
            for field_def in section_fields:
                if isinstance(field_def, dict) and 'name' in field_def:
                    fields.append(field_def['name'])
    
    return fields


def fill_missing_fields(sample: Dict[str, Any], schema_fields: List[str]) -> Dict[str, Any]:
    """Ensure all schema fields are present in sample, filling missing with null."""
    filled = {}
    for field in schema_fields:
        filled[field] = sample.get(field, None)
    # Add any extra fields that were extracted but not in schema
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
        logger.error("Invalid YAML in %s: %s", cfg_path, e)
        return {}
    except IOError as e:
        logger.error("Cannot read %s: %s", cfg_path, e)
        return {}


def load_stage_prompt(stages_dir: str, stage_file: str) -> str:
    """Load prompt template for a specific stage."""
    prompt_path = Path(stages_dir) / stage_file
    if not prompt_path.exists():
        raise FileNotFoundError(f"Stage prompt not found: {prompt_path}")
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()


def extract_chiral_hints(text: str) -> str:
    """Extract chiral-related hints from PDF text to help LLM locate data.
    
    Args:
        text: Full PDF text.
        
    Returns:
        String with hints or empty string.
    """
    import re
    hints = []
    
    # Chirality patterns
    chiral_patterns = [
        r'(?:L-|D-|R-|S-)\s*[A-Z][a-z]+',  # L-cysteine, D-penicillamine
        r'(?:enantiomer|chiral|enantioselective)',  # Chiral keywords
        r'(?:\(\+\)|\(\-\)|\+/-|-/\+)',  # Optical rotation
    ]
    
    for p in chiral_patterns:
        matches = re.findall(p, text, re.IGNORECASE)
        if matches:
            unique_matches = list(set(matches))[:5]
            hints.append(f'Chiral mentions: {", ".join(unique_matches)}')
            break
    
    # Enantioselectivity patterns
    ef_patterns = [
        r'(?:EF|enantioselectivity factor)\s*=?\s*(\d+\.?\d*)',
        r'selectivity.*?(\d+\.?\d*)\s*(?:fold|times)',
    ]
    for p in ef_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            hints.append(f'Enantioselectivity: {m.group(1)}')
            break
    
    # CPL/glum patterns
    cpl_patterns = [
        r'glum\s*=?\s*([+-]?\d+\.?\d*)',
        r'(?:CPL|circularly polarized luminescence)',
    ]
    for p in cpl_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            if 'glum' in p.lower():
                hints.append(f'glum value: {m.group(1)}')
            else:
                hints.append('CPL-active probe')
            break
    
    # Emission patterns
    em_patterns = [
        r'(?:emission|Em|λem|PL peak).*?(\d{3})\s*nm',
        r'(\d{3})\s*nm.*?(?:emission|fluorescence|PL)',
    ]
    for p in em_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 300 <= val <= 900:
                hints.append(f'Emission wavelength: ~{val} nm')
                break
    
    # Size patterns
    size_patterns = [
        r'(?:diameter|size|particle size).*?(\d+\.?\d*)\s*nm',
        r'(\d+\.?\d*)\s*nm.*?(?:diameter|particles)',
    ]
    for p in size_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if 1 <= val <= 500:
                hints.append(f'Particle size: ~{val} nm')
                break
    
    if hints:
        return '\n## CHIRAL HINTS (extracted from text)\n' + '\n'.join(hints)
    return ''


def build_stage_prompt(
    stage_prompt: str,
    pdf_text: str,
    schema_fields: Optional[List[str]] = None,
    max_text_length: int = 30000
) -> str:
    """Build the full extraction prompt with PDF content and schema context."""
    # Truncate text if too long
    if len(pdf_text) > max_text_length:
        half = max_text_length // 2
        truncated_text = pdf_text[:half] + "\n\n...[TRUNCATED]...\n\n" + pdf_text[-half:]
    else:
        truncated_text = pdf_text
    
    # Build schema summary for LLM context
    schema_hint = ""
    if schema_fields:
        schema_hint = f"""
## EXPECTED OUTPUT FIELDS
Your JSON output should contain these fields (use null for missing numeric values, "Not Specified" for missing strings):
{', '.join(schema_fields)}
"""
    
    # Add chiral hints to help model locate values
    chiral_hints = extract_chiral_hints(pdf_text)
    
    return f"""{stage_prompt}
{schema_hint}
{chiral_hints}
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
    schema_fields: Optional[List[str]] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """Run a single extraction stage."""
    full_prompt = build_stage_prompt(stage_prompt, pdf_text, schema_fields=schema_fields)
    
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
        logger.warning("Stage %s value error: %s", stage_name, e)
        raise
    except KeyError as e:
        logger.warning("Stage %s missing key: %s", stage_name, e)
        raise
    except Exception as e:
        error_str = str(e).lower()
        if images and any(kw in error_str for kw in ['image', 'multimodal', 'vision', 'unsupported', 'content_type']):
            logger.warning("Stage %s failed: Model may not support image input.", stage_name)
        else:
            logger.error("Stage %s failed: %s", stage_name, e)
        raise


def run_chiral_extraction(
    pdf_path: str,
    cfg: Dict[str, Any],
    stages_dir: str,
    output_dir: str,
    schema_path: str,
    verbose: bool = True
) -> Dict[str, Any]:
    """Run chiral nanoprobe extraction on a single PDF."""
    
    # Load schema from YAML
    try:
        schema = load_schema_from_yaml(schema_path)
        schema_fields = get_schema_field_names(schema)
        if verbose:
            logger.info("Loaded %d fields from schema_chiral.yml", len(schema_fields))
    except (FileNotFoundError, yaml.YAMLError) as e:
        return {"status": "error", "message": f"Schema load error: {e}"}
    
    # Step 1: Parse PDF
    if verbose:
        logger.info("[1/3] Parsing PDF...")
    
    pdf_data = parse_pdf(pdf_path)
    if "error" in pdf_data:
        return {"status": "error", "message": pdf_data["error"]}
    
    pdf_text = pdf_data.get("text", "")
    if not pdf_text.strip():
        return {"status": "error", "message": "No text extracted from PDF"}
    
    if verbose:
        logger.info("Extracted %d chars from %d pages", len(pdf_text), pdf_data['metadata'].get('page_count', 0))
    
    # Step 2: Get enabled models
    enabled_models = [m for m in cfg.get('models', []) if m.get('enabled', True)]
    if not enabled_models:
        return {"status": "error", "message": "No enabled models in llm_backends.yml"}
    
    model_ids = [m['id'] for m in enabled_models]
    mmc = MultiModelClient(cfg)
    
    if verbose:
        logger.info("[2/3] Running chiral extraction with %d model(s): %s", len(model_ids), ', '.join(model_ids))
    
    # Step 3: Run extraction
    stage = STAGES[0]
    stage_prompt = load_stage_prompt(stages_dir, stage["file"])
    
    all_samples = []
    
    for model_id in model_ids:
        try:
            if verbose:
                logger.info("Extracting with %s...", model_id)
            
            result = run_single_stage(
                mmc, model_id, stage_prompt, pdf_text, stage["name"],
                schema_fields=schema_fields, verbose=False
            )
            
            # Extract samples from result
            samples = result.get('samples', [])
            if not samples and result:
                samples = [result]
            
            for s in samples:
                if isinstance(s, dict):
                    s['_extracted_by'] = model_id
                    all_samples.append(s)
            
            if verbose:
                logger.info("%s extracted %d sample(s)", model_id, len(samples))
                
        except Exception as e:
            logger.warning("%s failed: %s", model_id, e)
    
    if not all_samples:
        return {"status": "error", "message": "No samples extracted"}
    
    # Add paper metadata to each sample
    paper_metadata = {
        "title": Path(pdf_path).stem,
        "source_pdf": pdf_path
    }
    
    filled_samples = []
    for sample in all_samples:
        sample.update({f"paper_{k}": v for k, v in paper_metadata.items()})
        sample['_source_pdf'] = pdf_path
        sample['_models_used'] = model_ids
        filled_sample = fill_missing_fields(sample, schema_fields)
        filled_samples.append(filled_sample)
    
    if verbose:
        logger.info("[3/3] Saving results...")
    
    # Save results
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    output = {
        'pdf': pdf_path,
        'paper_metadata': paper_metadata,
        'samples': filled_samples,
        'meta': {
            'models_used': model_ids,
            'sample_count': len(filled_samples),
            'schema_version': 'chiral_v1.0'
        }
    }
    
    fn = out_dir / (Path(pdf_path).stem + '.json')
    with open(fn, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    return {"status": "ok", "output_path": str(fn), "sample_count": len(filled_samples)}


def main():
    parser = argparse.ArgumentParser(description='Extract chiral nanoprobe data from PDFs')
    parser.add_argument('--pdf_dir', type=str, default='outputs/chiral_literature/PDF',
                        help='Directory containing PDF files')
    parser.add_argument('--out_dir', type=str, default='outputs/chiral_extraction',
                        help='Output directory for extracted JSON files')
    parser.add_argument('--cfg', type=str, default='configs/extraction/llm_backends.yml',
                        help='LLM configuration file')
    parser.add_argument('--schema', type=str, default='configs/extraction/schema_chiral.yml',
                        help='Schema definition file')
    parser.add_argument('--stages_dir', type=str, default='configs/extraction/stages',
                        help='Directory containing stage prompt files')
    parser.add_argument('--verbose', action='store_true', default=True,
                        help='Print progress messages')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    
    # Load configuration
    cfg = load_config(args.cfg)
    
    # Find PDF files
    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.exists():
        logger.error("PDF directory not found: %s", args.pdf_dir)
        return
    
    pdf_files = list(pdf_dir.glob('*.pdf'))
    logger.info("Found %d PDF files in %s", len(pdf_files), args.pdf_dir)
    
    # Process each PDF
    results = []
    for i, pdf_path in enumerate(pdf_files, 1):
        logger.info("\n[%d/%d] Processing: %s", i, len(pdf_files), pdf_path.name)
        
        result = run_chiral_extraction(
            str(pdf_path),
            cfg,
            args.stages_dir,
            args.out_dir,
            args.schema,
            verbose=args.verbose
        )
        
        results.append({
            'file': pdf_path.name,
            **result
        })
        
        if result['status'] == 'ok':
            logger.info("  Success: %d samples extracted", result.get('sample_count', 0))
        else:
            logger.warning("  Failed: %s", result.get('message', 'unknown error'))
    
    # Summary
    success_count = sum(1 for r in results if r['status'] == 'ok')
    total_samples = sum(r.get('sample_count', 0) for r in results if r['status'] == 'ok')
    
    logger.info("\n" + "="*60)
    logger.info("Extraction Complete!")
    logger.info("  PDFs processed: %d", len(pdf_files))
    logger.info("  Successful: %d", success_count)
    logger.info("  Failed: %d", len(pdf_files) - success_count)
    logger.info("  Total samples: %d", total_samples)
    logger.info("  Output directory: %s", args.out_dir)
    logger.info("="*60)


if __name__ == "__main__":
    main()