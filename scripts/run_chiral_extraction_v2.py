#!/usr/bin/env python3
# run_chiral_extraction_v2.py - 优化版手性纳米荧光探针提取
"""
优化特性：
1. 断点续传 - 支持中断后继续
2. 并行处理 - 多线程同时处理多个PDF
3. 数据验证 - 提取后自动验证数据质量
4. LLM重试 - 自动重试失败的调用
5. 详细日志 - 记录提取过程和统计
"""

import os
import sys
import argparse
import json
import logging
import yaml
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import concurrent.futures

# Fix Windows console encoding issues
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from etl_ensemble.pdf_parser import parse_pdf
from etl_ensemble.llm_multi_client import MultiModelClient

logger = logging.getLogger(__name__)

# 定义提取阶段
STAGES = [
    {"id": 1, "name": "chiral_extraction", "file": "stage1_chiral_extraction_v2.md", 
     "desc": "Chiral Nanoprobe Extraction", "multimodal": False},
]

# 必需字段列表
REQUIRED_FIELDS = ['core_material', 'chiral_source', 'emission_wavelength_nm', 'target_analyte']

# 重要字段列表
IMPORTANT_FIELDS = [
    'chiral_type', 'chiral_ligand', 'size_nm', 'quantum_yield_percent', 
    'limit_of_detection', 'response_type', 'enantioselectivity_factor'
]

# 有效枚举值
VALID_CHIRAL_TYPES = ['R', 'S', 'D', 'L', '(+)', '(-)', 'racemic', 'other', None]
VALID_RESPONSE_TYPES = ['turn-on', 'turn-off', 'ratiometric', 'colorimetric', 'cpl_on', 'cpl_off', 'other', None]


# ============================================================================
# 配置和工具函数
# ============================================================================

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
    for key, value in sample.items():
        if key not in filled:
            filled[key] = value
    return filled


def load_config(cfg_path: str) -> Dict[str, Any]:
    """Load YAML configuration file."""
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except (yaml.YAMLError, IOError) as e:
        logger.error("Failed to load config %s: %s", cfg_path, e)
        return {}


def load_stage_prompt(stages_dir: str, stage_file: str) -> str:
    """Load prompt template for a specific stage."""
    prompt_path = Path(stages_dir) / stage_file
    if not prompt_path.exists():
        # 回退到原版提示词
        prompt_path = Path(stages_dir) / "stage1_chiral_extraction.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Stage prompt not found: {prompt_path}")
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()


# ============================================================================
# 数据验证
# ============================================================================

def validate_sample(sample: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """验证提取的样本数据质量
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # 1. 检查必需字段
    for field in REQUIRED_FIELDS:
        if not sample.get(field):
            errors.append(f"Missing required field: {field}")
    
    # 2. 验证数值范围
    if sample.get('emission_wavelength_nm'):
        try:
            em = float(sample['emission_wavelength_nm'])
            if not (200 <= em <= 1500):
                errors.append(f"Emission wavelength {em} out of range (200-1500 nm)")
        except (ValueError, TypeError):
            errors.append(f"Invalid emission_wavelength_nm: {sample.get('emission_wavelength_nm')}")
    
    if sample.get('excitation_wavelength_nm'):
        try:
            ex = float(sample['excitation_wavelength_nm'])
            if not (200 <= ex <= 1200):
                errors.append(f"Excitation wavelength {ex} out of range (200-1200 nm)")
        except (ValueError, TypeError):
            errors.append(f"Invalid excitation_wavelength_nm: {sample.get('excitation_wavelength_nm')}")
    
    if sample.get('quantum_yield_percent'):
        try:
            qy = float(sample['quantum_yield_percent'])
            if not (0 <= qy <= 100):
                errors.append(f"Quantum yield {qy} out of range (0-100%)")
        except (ValueError, TypeError):
            errors.append(f"Invalid quantum_yield_percent: {sample.get('quantum_yield_percent')}")
    
    if sample.get('size_nm'):
        try:
            size = float(sample['size_nm'])
            if not (0.1 <= size <= 10000):
                errors.append(f"Size {size} out of range (0.1-10000 nm)")
        except (ValueError, TypeError):
            errors.append(f"Invalid size_nm: {sample.get('size_nm')}")
    
    # 3. 验证枚举值
    if sample.get('chiral_type') and sample['chiral_type'] not in VALID_CHIRAL_TYPES:
        errors.append(f"Invalid chiral_type: {sample['chiral_type']}")
    
    if sample.get('response_type') and sample['response_type'] not in VALID_RESPONSE_TYPES:
        errors.append(f"Invalid response_type: {sample['response_type']}")
    
    # 4. 验证enantioselectivity_factor
    if sample.get('enantioselectivity_factor'):
        try:
            ef = float(sample['enantioselectivity_factor'])
            if ef < 1.0:
                errors.append(f"Enantioselectivity factor should be >= 1.0, got {ef}")
        except (ValueError, TypeError):
            pass
    
    return len(errors) == 0, errors


def clean_sample(sample: Dict[str, Any]) -> Dict[str, Any]:
    """清理和标准化样本数据"""
    cleaned = sample.copy()
    
    # 清理数值字段
    numeric_fields = [
        'emission_wavelength_nm', 'excitation_wavelength_nm', 'size_nm',
        'quantum_yield_percent', 'enantioselectivity_factor', 'glum_value',
        'stokes_shift_nm', 'fluorescence_lifetime_ns', 'ph_value',
        'temperature_celsius', 'chiral_center_count'
    ]
    
    for field in numeric_fields:
        if field in cleaned and cleaned[field] is not None:
            try:
                cleaned[field] = float(cleaned[field])
            except (ValueError, TypeError):
                cleaned[field] = None
    
    # 标准化字符串字段
    string_fields = ['chiral_type', 'response_type', 'target_enantiomer']
    for field in string_fields:
        if field in cleaned and isinstance(cleaned[field], str):
            cleaned[field] = cleaned[field].strip()
    
    return cleaned


# ============================================================================
# 提示词构建
# ============================================================================

def extract_key_info(text: str) -> Dict[str, Any]:
    """从PDF文本中提取关键信息用于构建提示词"""
    import re
    info = {}
    
    # 提取波长信息
    em_match = re.search(r'(?:emission|Em|λem).*?(\d{3,4})\s*nm', text, re.IGNORECASE)
    if em_match:
        info['emission_hint'] = em_match.group(1)
    
    ex_match = re.search(r'(?:excitation|Ex|λex).*?(\d{3,4})\s*nm', text, re.IGNORECASE)
    if ex_match:
        info['excitation_hint'] = ex_match.group(1)
    
    # 提取尺寸信息
    size_match = re.search(r'(?:size|diameter).*?(\d+\.?\d*)\s*nm', text, re.IGNORECASE)
    if size_match:
        info['size_hint'] = size_match.group(1)
    
    # 提取量子产率
    qy_match = re.search(r'(?:QY|quantum yield).*?(\d+\.?\d*)\s*%', text, re.IGNORECASE)
    if qy_match:
        info['qy_hint'] = qy_match.group(1)
    
    # 提取手性相关关键词
    chiral_matches = re.findall(r'(?:L-|D-|R-|S-)[A-Za-z]+', text)
    if chiral_matches:
        info['chiral_mentions'] = list(set(chiral_matches))[:5]
    
    return info


def build_stage_prompt(
    stage_prompt: str,
    pdf_text: str,
    schema_fields: Optional[List[str]] = None,
    max_text_length: int = 40000
) -> str:
    """构建完整的提取提示词（优化版）"""
    
    # 截断过长的文本
    if len(pdf_text) > max_text_length:
        half = max_text_length // 2
        truncated_text = pdf_text[:half] + "\n\n...[TRUNCATED]...\n\n" + pdf_text[-half:]
    else:
        truncated_text = pdf_text
    
    # 提取关键信息
    key_info = extract_key_info(pdf_text)
    
    # 构建关键信息提示
    hints_section = ""
    if key_info:
        hints_parts = []
        if 'emission_hint' in key_info:
            hints_parts.append(f"Emission wavelength: ~{key_info['emission_hint']} nm")
        if 'excitation_hint' in key_info:
            hints_parts.append(f"Excitation wavelength: ~{key_info['excitation_hint']} nm")
        if 'size_hint' in key_info:
            hints_parts.append(f"Particle size: ~{key_info['size_hint']} nm")
        if 'qy_hint' in key_info:
            hints_parts.append(f"Quantum yield: ~{key_info['qy_hint']}%")
        if 'chiral_mentions' in key_info:
            hints_parts.append(f"Chiral molecules found: {', '.join(key_info['chiral_mentions'])}")
        
        if hints_parts:
            hints_section = "\n## KEY INFORMATION EXTRACTED FROM TEXT\n" + "\n".join(hints_parts) + "\n"
    
    # 构建schema提示（精简版）
    schema_hint = ""
    if schema_fields:
        # 只列出核心字段
        core_fields = [f for f in schema_fields if f in REQUIRED_FIELDS + IMPORTANT_FIELDS]
        schema_hint = f"""
## PRIORITY FIELDS (Focus on these)
Required: {', '.join(REQUIRED_FIELDS)}
Important: {', '.join(IMPORTANT_FIELDS)}
"""
    
    return f"""{stage_prompt}
{schema_hint}
{hints_section}
---

## Paper Content

{truncated_text}
"""


# ============================================================================
# LLM调用（带重试）
# ============================================================================

def call_llm_with_retry(
    mmc: MultiModelClient,
    model_id: str,
    prompt: str,
    schema: Dict,
    max_retries: int = 3,
    timeout: int = 120
) -> Dict[str, Any]:
    """带重试机制的LLM调用"""
    import time
    
    last_error = None
    for attempt in range(max_retries):
        try:
            out = mmc.extract(model_id, prompt, schema=schema)
            resp = out.get('resp', {})
            
            # 检查是否有错误
            if isinstance(resp, dict) and resp.get('error'):
                raise RuntimeError(f"Model error: {resp['error']}")
            
            return resp
            
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 指数退避
                logger.warning("LLM call failed (attempt %d/%d), retrying in %ds: %s", 
                             attempt + 1, max_retries, wait_time, str(e)[:100])
                time.sleep(wait_time)
            else:
                logger.error("LLM call failed after %d attempts: %s", max_retries, str(e)[:200])
    
    raise last_error


# ============================================================================
# 单个PDF处理
# ============================================================================

def process_single_pdf(
    pdf_path: str,
    cfg: Dict[str, Any],
    stages_dir: str,
    schema_fields: List[str],
    stage_prompt: str,
    verbose: bool = True
) -> Dict[str, Any]:
    """处理单个PDF文件（优化版）"""
    
    start_time = time.time()
    pdf_name = Path(pdf_path).name
    
    try:
        # Step 1: 解析PDF
        pdf_data = parse_pdf(pdf_path)
        if "error" in pdf_data:
            return {
                "status": "error",
                "file": pdf_name,
                "message": pdf_data["error"],
                "elapsed_seconds": time.time() - start_time
            }
        
        pdf_text = pdf_data.get("text", "")
        if not pdf_text.strip():
            return {
                "status": "error",
                "file": pdf_name,
                "message": "No text extracted from PDF",
                "elapsed_seconds": time.time() - start_time
            }
        
        # Step 2: 获取启用的模型
        enabled_models = [m for m in cfg.get('models', []) if m.get('enabled', True)]
        if not enabled_models:
            return {
                "status": "error",
                "file": pdf_name,
                "message": "No enabled models in llm_backends.yml",
                "elapsed_seconds": time.time() - start_time
            }
        
        model_ids = [m['id'] for m in enabled_models]
        
        # Step 3: 构建提示词
        full_prompt = build_stage_prompt(stage_prompt, pdf_text, schema_fields=schema_fields)
        
        # Step 4: 调用LLM（带重试）
        mmc = MultiModelClient(cfg)
        all_samples = []
        
        for model_id in model_ids:
            try:
                resp = call_llm_with_retry(
                    mmc, model_id, full_prompt, 
                    schema={"type": "object"},
                    max_retries=2
                )
                
                # 解析结果
                samples = resp.get('samples', [])
                if not samples and resp:
                    samples = [resp]
                
                for s in samples:
                    if isinstance(s, dict):
                        s['_extracted_by'] = model_id
                        all_samples.append(s)
                        
            except Exception as e:
                logger.warning("Model %s failed for %s: %s", model_id, pdf_name, str(e)[:100])
        
        if not all_samples:
            return {
                "status": "error",
                "file": pdf_name,
                "message": "No samples extracted from any model",
                "elapsed_seconds": time.time() - start_time
            }
        
        # Step 5: 验证和清理
        validated_samples = []
        validation_errors = []
        
        for sample in all_samples:
            cleaned = clean_sample(sample)
            is_valid, errors = validate_sample(cleaned)
            
            if is_valid:
                validated_samples.append(cleaned)
            else:
                validation_errors.extend(errors)
                # 仍然保留，但标记为需要人工审核
                cleaned['_validation_errors'] = errors
                validated_samples.append(cleaned)
        
        # Step 6: 填充缺失字段
        paper_metadata = {
            "title": Path(pdf_path).stem,
            "source_pdf": pdf_path,
            "page_count": pdf_data.get('metadata', {}).get('page_count', 0),
            "text_length": len(pdf_text)
        }
        
        filled_samples = []
        for sample in validated_samples:
            sample.update({f"paper_{k}": v for k, v in paper_metadata.items()})
            sample['_source_pdf'] = pdf_path
            sample['_models_used'] = model_ids
            sample['_extraction_time'] = datetime.now().isoformat()
            filled_sample = fill_missing_fields(sample, schema_fields)
            filled_samples.append(filled_sample)
        
        elapsed = time.time() - start_time
        
        return {
            "status": "ok",
            "file": pdf_name,
            "sample_count": len(filled_samples),
            "valid_count": sum(1 for s in filled_samples if not s.get('_validation_errors')),
            "validation_errors": validation_errors,
            "elapsed_seconds": elapsed,
            "samples": filled_samples,
            "paper_metadata": paper_metadata
        }
        
    except Exception as e:
        logger.error("Failed to process %s: %s", pdf_name, str(e)[:200])
        return {
            "status": "error",
            "file": pdf_name,
            "message": str(e)[:200],
            "elapsed_seconds": time.time() - start_time
        }


# ============================================================================
# 检查点管理
# ============================================================================

def load_checkpoint(checkpoint_path: str) -> Dict[str, Any]:
    """加载检查点"""
    if os.path.exists(checkpoint_path):
        try:
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load checkpoint: %s", e)
    return {'processed': [], 'failed': [], 'timestamp': None}


def save_checkpoint(checkpoint_path: str, processed: List[str], failed: List[str]):
    """保存检查点"""
    checkpoint = {
        'processed': processed,
        'failed': failed,
        'timestamp': datetime.now().isoformat()
    }
    try:
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(checkpoint, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("Failed to save checkpoint: %s", e)


# ============================================================================
# 保存结果
# ============================================================================

def save_extraction_result(result: Dict[str, Any], output_dir: str):
    """保存单个PDF的提取结果"""
    if result['status'] != 'ok':
        return
    
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 构建输出JSON
    output = {
        'pdf': result['file'],
        'paper_metadata': result.get('paper_metadata', {}),
        'samples': result.get('samples', []),
        'meta': {
            'sample_count': result.get('sample_count', 0),
            'valid_count': result.get('valid_count', 0),
            'extraction_time': datetime.now().isoformat(),
            'elapsed_seconds': result.get('elapsed_seconds', 0)
        }
    }
    
    # 保存文件
    fn = out_dir / (Path(result['file']).stem + '.json')
    with open(fn, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


# ============================================================================
# 主函数（支持并行处理）
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Extract chiral nanoprobe data from PDFs (Optimized)')
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
    parser.add_argument('--workers', type=int, default=4,
                        help='Number of parallel workers (default: 4)')
    parser.add_argument('--verbose', action='store_true', default=True,
                        help='Print progress messages')
    parser.add_argument('--resume', action='store_true', default=True,
                        help='Resume from checkpoint (skip already processed files)')
    
    args = parser.parse_args()
    
    # Setup logging（同时输出到控制台和文件）
    # 获取项目根目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    log_dir = os.path.join(project_root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # 生成带有时间戳的日志文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"extraction_{timestamp}.log")
    
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
    logger.info("Starting chiral nanoprobe data extraction")
    logger.info("Log file: %s", log_file)
    logger.info("=" * 60)
    
    # Load configuration
    cfg = load_config(args.cfg)
    
    # Load schema
    try:
        schema = load_schema_from_yaml(args.schema)
        schema_fields = get_schema_field_names(schema)
        logger.info("Loaded %d fields from schema", len(schema_fields))
    except Exception as e:
        logger.error("Failed to load schema: %s", e)
        return
    
    # Load stage prompt
    try:
        stage = STAGES[0]
        stage_prompt = load_stage_prompt(args.stages_dir, stage["file"])
        logger.info("Loaded stage prompt from %s", stage["file"])
    except Exception as e:
        logger.error("Failed to load stage prompt: %s", e)
        return
    
    # Find PDF files
    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.exists():
        logger.error("PDF directory not found: %s", args.pdf_dir)
        return
    
    pdf_files = sorted(pdf_dir.glob('*.pdf'))
    logger.info("Found %d PDF files in %s", len(pdf_files), args.pdf_dir)
    
    # 加载检查点（如果启用断点续传）
    checkpoint_path = os.path.join(args.out_dir, 'checkpoint.json')
    if args.resume:
        checkpoint = load_checkpoint(checkpoint_path)
        processed_files = set(checkpoint.get('processed', []))
        pdf_files = [f for f in pdf_files if f.name not in processed_files]
        logger.info("Resuming: skipping %d already processed files, %d remaining", 
                   len(processed_files), len(pdf_files))
    
    if not pdf_files:
        logger.info("No PDF files to process")
        return
    
    # 创建输出目录
    os.makedirs(args.out_dir, exist_ok=True)
    
    # 并行处理
    logger.info("Starting extraction with %d workers...", args.workers)
    start_time = time.time()
    
    all_results = []
    processed_names = []
    failed_names = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        # 提交所有任务
        future_to_pdf = {
            executor.submit(
                process_single_pdf, 
                str(pdf_path), 
                cfg, 
                args.stages_dir, 
                schema_fields, 
                stage_prompt, 
                args.verbose
            ): pdf_path
            for pdf_path in pdf_files
        }
        
        # 处理完成的任务
        completed = 0
        for future in concurrent.futures.as_completed(future_to_pdf):
            pdf_path = future_to_pdf[future]
            completed += 1
            
            try:
                result = future.result()
                all_results.append(result)
                
                if result['status'] == 'ok':
                    # 保存结果
                    save_extraction_result(result, args.out_dir)
                    processed_names.append(result['file'])
                    
                    logger.info("[%d/%d] ✓ %s: %d samples (%d valid) in %.1fs", 
                               completed, len(pdf_files), result['file'],
                               result.get('sample_count', 0), 
                               result.get('valid_count', 0),
                               result.get('elapsed_seconds', 0))
                else:
                    failed_names.append(result['file'])
                    logger.warning("[%d/%d] ✗ %s: %s", 
                                  completed, len(pdf_files), result['file'], 
                                  result.get('message', 'unknown error'))
                
                # 定期保存检查点
                if completed % 10 == 0:
                    save_checkpoint(checkpoint_path, processed_names, failed_names)
                    
            except Exception as e:
                failed_names.append(pdf_path.name)
                logger.error("[%d/%d] ✗ %s: Exception: %s", 
                            completed, len(pdf_files), pdf_path.name, str(e)[:200])
    
    # 最终保存检查点
    save_checkpoint(checkpoint_path, processed_names, failed_names)
    
    # 统计
    total_time = time.time() - start_time
    success_count = sum(1 for r in all_results if r['status'] == 'ok')
    total_samples = sum(r.get('sample_count', 0) for r in all_results if r['status'] == 'ok')
    valid_samples = sum(r.get('valid_count', 0) for r in all_results if r['status'] == 'ok')
    avg_time = total_time / len(pdf_files) if pdf_files else 0
    
    # 保存提取日志
    log_path = os.path.join(args.out_dir, 'extraction_log.json')
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump({
            'summary': {
                'total_pdfs': len(pdf_files),
                'successful': success_count,
                'failed': len(pdf_files) - success_count,
                'total_samples': total_samples,
                'valid_samples': valid_samples,
                'total_time_seconds': total_time,
                'avg_time_per_pdf': avg_time,
                'workers': args.workers
            },
            'results': all_results
        }, f, indent=2, ensure_ascii=False)
    
    # 打印摘要
    logger.info("\n" + "=" * 60)
    logger.info("Extraction Complete!")
    logger.info("  PDFs processed: %d", len(pdf_files))
    logger.info("  Successful: %d", success_count)
    logger.info("  Failed: %d", len(pdf_files) - success_count)
    logger.info("  Total samples: %d", total_samples)
    logger.info("  Valid samples: %d", valid_samples)
    logger.info("  Total time: %.1f minutes", total_time / 60)
    logger.info("  Avg time per PDF: %.1f seconds", avg_time)
    logger.info("  Output directory: %s", args.out_dir)
    logger.info("  Checkpoint: %s", checkpoint_path)
    logger.info("  Extraction log: %s", log_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()