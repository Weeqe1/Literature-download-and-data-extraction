# etl_core/figure_extractor.py
import os, json
from pathlib import Path
from typing import Dict, Any, List

def _safe_import(name):
    try:
        return __import__(name)
    except Exception:
        return None

fitz = _safe_import("fitz")

try:
    from .safe_pixmap import save_pixmap_safe, choose_ext_for_pixmap
except Exception:
    from safe_pixmap import save_pixmap_safe, choose_ext_for_pixmap  # type: ignore

def extract_figures(pdf_path: str, layout_json: str, out_dir: str) -> List[Dict[str, Any]]:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    results = []
    captions = []
    try:
        with open(layout_json, "r", encoding="utf-8") as f:
            meta = json.load(f)
            captions = meta.get("captions", [])
    except Exception:
        pass

    if not fitz:
        ev_dir = Path("data/outputs/evidence")
        for p in ev_dir.glob(f"{Path(pdf_path).with_suffix('').name}_p*/*.*"):
            results.append({"page": None, "path": str(p), "caption": None, "method": "fallback_evidence"})
        out_meta = Path(out_dir) / "figures_meta.json"
        with open(out_meta, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        return results

    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc, start=1):
        imgs = page.get_images(full=True)
        for idx, img in enumerate(imgs, start=1):
            xref = img[0]
            pix = fitz.Pixmap(doc, xref)
            ext = choose_ext_for_pixmap(pix)
            tentative = Path(out_dir) / f"fig_p{i}_{idx}{ext}"
            final_path = save_pixmap_safe(pix, str(tentative))
            cap_text = None
            for c in captions:
                if c.get("page") == i:
                    cap_text = c.get("caption")
                    break
            results.append({"page": i, "path": str(final_path), "caption": cap_text, "method": "pymupdf"})
    out_meta = Path(out_dir) / "figures_meta.json"
    with open(out_meta, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return results
