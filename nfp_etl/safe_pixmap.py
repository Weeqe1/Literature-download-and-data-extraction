
# nfp_etl/safe_pixmap.py
from __future__ import annotations
import os
import fitz  # PyMuPDF

def save_pixmap_safe(pix: fitz.Pixmap, out_path: str) -> str:
    """Save a Pixmap safely.
    Strategy:
    - If colorspace is None (mask/indexed), avoid conversion and *force PNG*.
    - If alpha exists, strip alpha for JPEG; if write fails, fall back to PNG.
    - If channel count <3, convert to RGB.
    Returns the *actual* path written (may differ in extension).
    """
    try:
        ext = os.path.splitext(out_path)[1].lower()

        # If source has no colorspace (masks etc.), saving to PNG directly is safest.
        if getattr(pix, 'colorspace', None) is None:
            # force PNG extension
            if ext not in ('.png',):
                out_path = out_path.rsplit('.', 1)[0] + '.png'
            pix.save(out_path)
            return out_path

        # Convert grayscale to RGB if needed
        if getattr(pix, 'n', 0) < 3:
            pix = fitz.Pixmap(fitz.csRGB, pix)

        # Handle alpha for JPEG
        if getattr(pix, 'alpha', 0):
            if ext in ('.jpg', '.jpeg'):
                # strip alpha before JPEG
                pix = fitz.Pixmap(fitz.csRGB, pix)

        # Try desired ext
        try:
            pix.save(out_path)
            return out_path
        except RuntimeError:
            # Fallback to PNG
            out_png = out_path.rsplit('.', 1)[0] + '.png'
            pix.save(out_png)
            return out_png

    finally:
        try:
            pix = None
        except Exception:
            pass

def choose_ext_for_pixmap(pix: fitz.Pixmap) -> str:
    """Choose preferred extension: PNG if colorspace is None or alpha; else JPG."""
    if getattr(pix, 'colorspace', None) is None:
        return '.png'
    return '.png' if getattr(pix, 'alpha', 0) else '.jpg'
