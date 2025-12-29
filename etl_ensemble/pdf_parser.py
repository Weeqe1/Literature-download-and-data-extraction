# etl_ensemble/pdf_parser.py
"""PDF text and image extraction module.

Uses pdfplumber for text extraction and PyMuPDF (fitz) for images.
"""
import os
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

def _safe_import(name):
    try:
        return __import__(name)
    except Exception:
        return None

pdfplumber = _safe_import("pdfplumber")
fitz = _safe_import("fitz")


def extract_text_from_pdf(pdf_path: str) -> Dict[str, Any]:
    """Extract text content from PDF.
    
    Returns:
        Dict with keys:
            - pages: List of {page: int, text: str}
            - full_text: Concatenated text from all pages
            - page_count: Total number of pages
    """
    result = {"pages": [], "full_text": "", "page_count": 0}
    
    if pdfplumber:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                result["page_count"] = len(pdf.pages)
                all_text = []
                for i, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    result["pages"].append({"page": i, "text": text})
                    all_text.append(text)
                result["full_text"] = "\n\n".join(all_text)
        except Exception as e:
            result["error"] = f"pdfplumber error: {e}"
    elif fitz:
        try:
            doc = fitz.open(pdf_path)
            result["page_count"] = len(doc)
            all_text = []
            for i, page in enumerate(doc, start=1):
                text = page.get_text()
                result["pages"].append({"page": i, "text": text})
                all_text.append(text)
            result["full_text"] = "\n\n".join(all_text)
            doc.close()
        except Exception as e:
            result["error"] = f"fitz error: {e}"
    else:
        result["error"] = "No PDF library available. Install pdfplumber or PyMuPDF."
    
    return result


def extract_tables_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """Extract tables from PDF using pdfplumber."""
    tables = []
    if not pdfplumber:
        return tables
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                page_tables = page.extract_tables()
                for j, table in enumerate(page_tables):
                    tables.append({
                        "page": i,
                        "table_index": j,
                        "data": table
                    })
    except Exception:
        pass
    
    return tables


def detect_figure_captions(text: str) -> List[str]:
    """Detect figure/table captions from text."""
    captions = []
    pattern = re.compile(r'^(Figure|Fig\.|图|Table|表)\s*[\dA-Za-z]+[.:]\s*.*', re.I | re.M)
    for match in pattern.finditer(text):
        captions.append(match.group().strip())
    return captions


def parse_pdf(pdf_path: str) -> Dict[str, Any]:
    """Main function to parse PDF and extract all relevant content.
    
    Returns:
        Dict with:
            - text: Full text content
            - pages: Per-page text
            - tables: Extracted tables
            - captions: Detected figure/table captions
            - metadata: Basic PDF info
    """
    result = {
        "pdf_path": pdf_path,
        "text": "",
        "pages": [],
        "tables": [],
        "captions": [],
        "metadata": {
            "filename": Path(pdf_path).name,
            "stem": Path(pdf_path).stem
        }
    }
    
    # Extract text
    text_result = extract_text_from_pdf(pdf_path)
    result["text"] = text_result.get("full_text", "")
    result["pages"] = text_result.get("pages", [])
    result["metadata"]["page_count"] = text_result.get("page_count", 0)
    
    if "error" in text_result:
        result["error"] = text_result["error"]
    
    # Extract tables
    result["tables"] = extract_tables_from_pdf(pdf_path)
    
    # Detect captions
    result["captions"] = detect_figure_captions(result["text"])
    
    return result


def truncate_text(text: str, max_chars: int = 50000) -> str:
    """Truncate text to fit within LLM context limits."""
    if len(text) <= max_chars:
        return text
    # Keep beginning and end
    half = max_chars // 2
    return text[:half] + "\n\n...[TRUNCATED]...\n\n" + text[-half:]
