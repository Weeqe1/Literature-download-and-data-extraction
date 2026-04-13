"""PDF integrity checking and cleanup module.

Provides functions to validate downloaded PDFs and remove corrupted files.
"""

import os
from typing import List, Dict, Any, Tuple

import pandas as pd

import logging
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional PDF reader
# ---------------------------------------------------------------------------
try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None


def check_pdf_valid(path: str) -> bool:
    """Check if PDF can be opened and has at least 1 page.

    Args:
        path: Path to PDF file.

    Returns:
        True if the PDF appears valid.
    """
    if not os.path.exists(path):
        return False
    if PdfReader is None:
        # best-effort: check file size > 1KB and starts with %PDF
        try:
            with open(path, "rb") as fh:
                head = fh.read(6)
                if not head.startswith(b"%PDF"):
                    return False
                fh.seek(0, 2)
                size = fh.tell()
                return size > 1024
        except Exception:
            return False
    try:
        with open(path, "rb") as fh:
            pdf = PdfReader(fh)
            if getattr(pdf, "pages", None) is None:
                return False
            if len(pdf.pages) < 1:
                return False
        return True
    except Exception:
        return False


def export_rejected_audit(audit_rows: List[Dict[str, Any]], out_path: str, verbose: bool = True) -> None:
    """Export locally filtered-out samples to an audit Excel file.

    Args:
        audit_rows: List of rejected item dicts.
        out_path: Output Excel path.
        verbose: Log messages.
    """
    if not audit_rows:
        if verbose:
            logger.info("[Audit] no filtered-out samples to export")
        return
    try:
        df = pd.DataFrame(audit_rows)
        df.to_excel(out_path, index=False)
        if verbose:
            logger.info("[Audit] exported filtered-out samples: %d -> %s", len(df), out_path)
    except Exception as e:
        logger.error("[Audit] failed to export audit file: %s", e)


def pdf_check_and_cleanup(
    excel_path: str,
    pdf_base_dir: str,
    backup: bool = True,
    verbose: bool = True,
    log_each: bool = False,
    remove_invalid_rows: bool = False,
) -> Tuple[int, int]:
    """Check each PDF path listed in the CSV file and clean up invalids.

    Args:
        excel_path: Path to CSV file with pdf_path column.
        pdf_base_dir: Base directory where PDFs are stored.
        backup: If True, write checked results to a separate _check.csv file.
        verbose: Log summary.
        log_each: Log each invalid PDF individually.
        remove_invalid_rows: If True, remove rows with invalid PDFs entirely.

    Returns:
        Tuple of (checked_count, invalid_count).
    """
    if not os.path.exists(excel_path):
        if verbose:
            logger.warning("[PDF-Check] CSV not found: %s", excel_path)
        return 0, 0

    df = pd.read_csv(excel_path, encoding='utf-8-sig')
    if df.empty:
        return 0, 0

    checked = 0
    invalid = 0
    dropped_rows = 0
    to_keep = []

    for idx, row in df.iterrows():
        pdfp = row.get("pdf_path")
        if not pdfp or not isinstance(pdfp, str) or not pdfp.strip():
            row["pdf_valid"] = False
            to_keep.append(row)
            continue

        checked += 1
        if not os.path.exists(pdfp):
            invalid += 1
            if verbose and log_each:
                logger.info("[PDF-Check] missing: %s", pdfp)
            if remove_invalid_rows:
                dropped_rows += 1
                continue
            row["pdf_path"] = None
            row["pdf_valid"] = False
            to_keep.append(row)
            continue

        ok = check_pdf_valid(pdfp)
        if not ok:
            invalid += 1
            try:
                os.remove(pdfp)
            except Exception:
                pass
            if verbose and log_each:
                logger.info("[PDF-Check] invalid/corrupt: %s", pdfp)
            if remove_invalid_rows:
                dropped_rows += 1
                continue
            row["pdf_path"] = None
            row["pdf_valid"] = False
            to_keep.append(row)
            continue

        row["pdf_valid"] = True
        to_keep.append(row)

    if backup:
        base_name = excel_path.rsplit('.csv', 1)[0]
        checked_path = base_name + '_check.csv'
    else:
        checked_path = excel_path

    if to_keep:
        new_df = pd.DataFrame(to_keep)
    else:
        new_df = pd.DataFrame(columns=df.columns)
    new_df.to_csv(checked_path, index=False, encoding='utf-8-sig')

    if verbose:
        logger.info("[PDF-Check] completed: checked_pdfs=%d, invalid_pdfs=%d, dropped_rows=%d", checked, invalid, dropped_rows)
    return checked, invalid
