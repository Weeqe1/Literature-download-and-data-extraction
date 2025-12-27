#!/usr/bin/env python3
# run_etl_ensemble.py - Multi-model extraction driver
import os, argparse, json, yaml, time
from pathlib import Path

from etl_ensemble.llm_multi_client import MultiModelClient
from etl_ensemble.consensus_engine import compare_outputs
from etl_ensemble.focused_reextractor import reextract
from etl_ensemble.human_review_manager import save_review_case

def load_config(cfg_path):
    with open(cfg_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def run_one_pdf(pdf_path, cfg, prompt_text, output_dir):
    mmc = MultiModelClient(cfg)
    model_ids = [m['id'] for m in cfg.get('models', [])]
    results = []
    for mid in model_ids:
        print(f"Calling model {mid}...")
        out = mmc.extract(mid, prompt_text)
        results.append(out)
    comp = compare_outputs(results, thresholds=cfg.get('thresholds'))
    # if no disagreements -> save agreed fields
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not comp.get('disagreed'):
        # merge agreed into a single record
        rec = {k:v['value'] for k,v in comp.get('agreed', {}).items()}
        rec['_models'] = model_ids
        fn = out_dir / (Path(pdf_path).stem + '.json')
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump({'pdf':pdf_path, 'record': rec, 'meta': comp}, f, ensure_ascii=False, indent=2)
        return {'status':'ok', 'saved': str(fn)}
    # else reextract focusing on disagreements
    print('Disagreements detected, performing focused re-extraction...')
    re_results = reextract(mmc, model_ids, prompt_text, comp.get('disagreed'), snippets=None)
    comp2 = compare_outputs(re_results, thresholds=cfg.get('thresholds'))
    if not comp2.get('disagreed'):
        rec = {k:v['value'] for k,v in comp2.get('agreed', {}).items()}
        fn = out_dir / (Path(pdf_path).stem + '.json')
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump({'pdf':pdf_path, 'record': rec, 'meta': comp2}, f, ensure_ascii=False, indent=2)
        return {'status':'ok_after_reextract', 'saved': str(fn)}
    # still disagrees -> save for review
    review_fn = save_review_case(out_dir, pdf_path, comp2)
    return {'status':'review', 'review_file': review_fn, 'meta': comp2}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pdf_dir', default='data/pdfs')
    parser.add_argument('--cfg', default='configs/llm_backends.yml')
    parser.add_argument('--out_dir', default='data/outputs/multi')
    parser.add_argument('--prompt_file', default='configs/prompts/paper_summarize.md')
    args = parser.parse_args()
    cfg = load_config(args.cfg)
    prompt_text = ''
    try:
        with open(args.prompt_file, 'r', encoding='utf-8') as f:
            prompt_text = f.read()
    except Exception:
        prompt_text = 'Extract canonical fields as JSON.'
    pdf_dir = Path(args.pdf_dir)
    pdfs = list(pdf_dir.glob('*.pdf'))
    print(f"Found {len(pdfs)} pdfs in {pdf_dir}")
    for p in pdfs:
        print('Processing', p)
        res = run_one_pdf(str(p), cfg, prompt_text, args.out_dir)
        print('Result:', res)
    print('Done')

if __name__ == '__main__':
    main()
