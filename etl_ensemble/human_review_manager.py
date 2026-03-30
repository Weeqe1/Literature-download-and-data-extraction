"""Human review manager for tracking files that need manual review."""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import logging
logger = logging.getLogger(__name__)


def save_review_case(out_dir: str, pdf_path: str, disagreements: dict) -> str:
    """Save a review case to disk.

    Args:
        out_dir: Directory to store review JSON files.
        pdf_path: Path to the PDF that has disagreements.
        disagreements: Dict of field disagreements.

    Returns:
        The file path of the saved case.
    """
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.basename(pdf_path)
    case = {
        'pdf': pdf_path,
        'base': base,
        'disagreements': disagreements,
        'timestamp': datetime.utcnow().isoformat(),
        'status': 'pending'
    }
    fn = os.path.join(out_dir, base + '.review.json')
    with open(fn, 'w', encoding='utf-8') as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    logger.info("Saved review case: %s", fn)
    return fn


def load_pending_reviews(review_dir: str) -> List[Dict[str, Any]]:
    """Load all pending review cases from a directory.

    Args:
        review_dir: Directory containing .review.json files.

    Returns:
        List of pending review case dicts.
    """
    if not os.path.isdir(review_dir):
        return []
    cases = []
    for fn in os.listdir(review_dir):
        if not fn.endswith('.review.json'):
            continue
        try:
            with open(os.path.join(review_dir, fn), 'r', encoding='utf-8') as f:
                case = json.load(f)
            if case.get('status', 'pending') == 'pending':
                case['_file'] = fn
                cases.append(case)
        except Exception as e:
            logger.warning("Failed to load review case %s: %s", fn, e)
    return cases


def mark_reviewed(review_dir: str, base_name: str, resolution: Dict[str, Any]) -> bool:
    """Mark a review case as resolved.

    Args:
        review_dir: Directory containing review JSON files.
        base_name: Base name of the PDF (without .review.json).
        resolution: Dict with resolution details.

    Returns:
        True if successfully marked, False otherwise.
    """
    fn = os.path.join(review_dir, base_name + '.review.json')
    if not os.path.exists(fn):
        logger.warning("Review case not found: %s", fn)
        return False
    try:
        with open(fn, 'r', encoding='utf-8') as f:
            case = json.load(f)
        case['status'] = 'reviewed'
        case['resolution'] = resolution
        case['reviewed_at'] = datetime.utcnow().isoformat()
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump(case, f, ensure_ascii=False, indent=2)
        logger.info("Marked as reviewed: %s", base_name)
        return True
    except Exception as e:
        logger.error("Failed to mark reviewed %s: %s", base_name, e)
        return False


def get_review_stats(review_dir: str) -> Dict[str, int]:
    """Get statistics about review cases.

    Args:
        review_dir: Directory containing review JSON files.

    Returns:
        Dict with 'total', 'pending', 'reviewed' counts.
    """
    if not os.path.isdir(review_dir):
        return {'total': 0, 'pending': 0, 'reviewed': 0}
    total = 0
    pending = 0
    reviewed = 0
    for fn in os.listdir(review_dir):
        if not fn.endswith('.review.json'):
            continue
        total += 1
        try:
            with open(os.path.join(review_dir, fn), 'r', encoding='utf-8') as f:
                case = json.load(f)
            if case.get('status') == 'reviewed':
                reviewed += 1
            else:
                pending += 1
        except Exception:
            pending += 1
    return {'total': total, 'pending': pending, 'reviewed': reviewed}


def export_review_report(review_dir: str, out_path: str) -> int:
    """Export all review cases to a single report file (JSON).

    Args:
        review_dir: Directory containing review JSON files.
        out_path: Output path for the consolidated report.

    Returns:
        Number of cases exported, or 0 if none found.
    """
    cases = []
    if not os.path.isdir(review_dir):
        return 0
    for fn in sorted(os.listdir(review_dir)):
        if not fn.endswith('.review.json'):
            continue
        try:
            with open(os.path.join(review_dir, fn), 'r', encoding='utf-8') as f:
                cases.append(json.load(f))
        except Exception:
            pass
    if not cases:
        return 0
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)
    logger.info("Exported %d review cases to %s", len(cases), out_path)
    return len(cases)
