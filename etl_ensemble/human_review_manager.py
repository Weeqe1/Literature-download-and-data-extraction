# nfp_etl_multi/review_manager.py
"""Track files requiring human review and write logs."""
import os, json
from datetime import datetime

def save_review_case(out_dir: str, pdf_path: str, disagreements: dict):
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.basename(pdf_path)
    case = {
        'pdf': pdf_path,
        'base': base,
        'disagreements': disagreements,
        'timestamp': datetime.utcnow().isoformat()
    }
    fn = os.path.join(out_dir, base + '.review.json')
    with open(fn, 'w', encoding='utf-8') as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    return fn
