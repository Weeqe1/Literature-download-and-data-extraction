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


def extract_images_from_pdf(
    pdf_path: str,
    max_images: int = 10,
    min_width: int = 100,
    min_height: int = 100,
    output_format: str = "png"
) -> List[Dict[str, Any]]:
    """Extract images from PDF using PyMuPDF (fitz).
    
    Args:
        pdf_path: Path to PDF file
        max_images: Maximum number of images to extract
        min_width: Minimum image width to include
        min_height: Minimum image height to include
        output_format: Image format (png or jpeg)
        
    Returns:
        List of dicts with:
            - page: Page number
            - index: Image index on page
            - width: Image width
            - height: Image height
            - base64: Base64 encoded image data
            - format: Image format (png/jpeg)
    """
    import base64
    import io
    
    images = []
    
    if not fitz:
        return images
    
    try:
        doc = fitz.open(pdf_path)
        image_count = 0
        
        for page_num, page in enumerate(doc, start=1):
            if image_count >= max_images:
                break
                
            # Get list of images on this page
            image_list = page.get_images(full=True)
            
            for img_index, img_info in enumerate(image_list):
                if image_count >= max_images:
                    break
                    
                xref = img_info[0]  # Image xref
                
                try:
                    # Extract image
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)
                    
                    # Filter by size
                    if width < min_width or height < min_height:
                        continue
                    
                    # Convert to base64
                    # For multimodal LLM, we need PNG or JPEG
                    if image_ext.lower() in ["png", "jpeg", "jpg"]:
                        b64_data = base64.b64encode(image_bytes).decode('utf-8')
                        mime_type = f"image/{image_ext.lower()}"
                        if image_ext.lower() == "jpg":
                            mime_type = "image/jpeg"
                    else:
                        # Convert other formats to PNG using PIL if available
                        try:
                            from PIL import Image
                            img = Image.open(io.BytesIO(image_bytes))
                            buffer = io.BytesIO()
                            img.save(buffer, format="PNG")
                            b64_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
                            mime_type = "image/png"
                        except ImportError:
                            # Skip if PIL not available
                            continue
                    
                    images.append({
                        "page": page_num,
                        "index": img_index,
                        "width": width,
                        "height": height,
                        "base64": b64_data,
                        "mime_type": mime_type,
                        "size_bytes": len(image_bytes)
                    })
                    image_count += 1
                    
                except Exception:
                    continue
        
        doc.close()
        
    except Exception as e:
        pass
    
    return images


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
