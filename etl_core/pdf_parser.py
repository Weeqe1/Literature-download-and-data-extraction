# etl_core/pdf_parser.py
import os, json, re
from pathlib import Path
from typing import Dict, Any, List

def _safe_import(name):
    try:
        return __import__(name)
    except Exception:
        return None

pdfplumber = _safe_import("pdfplumber")
fitz = _safe_import("fitz")

try:
    from .safe_pixmap import save_pixmap_safe, choose_ext_for_pixmap
except Exception:
    from safe_pixmap import save_pixmap_safe, choose_ext_for_pixmap  # type: ignore

def load_pdf(path: str) -> Dict[str, Any]:
    meta = {"pages": [], "images": []}
    if pdfplumber:
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                meta["pages"].append({"page": i, "text": text})

    if fitz:
        doc = fitz.open(path)
        for i, page in enumerate(doc, start=1):
            for img_index, img in enumerate(page.get_images(full=True), start=1):
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                img_dir = Path(path).with_suffix("").name + f"_p{i}"
                out_dir = Path("data/outputs/evidence") / img_dir
                out_dir.mkdir(parents=True, exist_ok=True)
                ext = choose_ext_for_pixmap(pix)
                tentative = out_dir / f"img_{img_index}{ext}"
                final_path = save_pixmap_safe(pix, str(tentative))
                meta["images"].append({"page": i, "path": str(final_path)})
    return meta

def detect_captions(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    caps = []
    pat = re.compile(r'^(Figure|Fig\.|图|Table|表)\s*[\dA-Za-z]+', re.I)
    for p in pages:
        for line in (p.get("text") or "").splitlines():
            if pat.match(line.strip()):
                caps.append({"page": p["page"], "caption": line.strip()})
    return caps

def run(pdf_path: str, staging_dir: str) -> str:
    Path(staging_dir).mkdir(parents=True, exist_ok=True)
    meta = load_pdf(pdf_path)
    meta["captions"] = detect_captions(meta["pages"])
    out_path = Path(staging_dir) / "layout.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return str(out_path)
