
# nfp_etl/spectrum_digitizer.py (patched imread for Unicode paths)
from typing import Dict, Any
def _safe_import(name):
    try:
        return __import__(name)
    except Exception:
        return None

cv2 = _safe_import("cv2")
np = _safe_import("numpy")

class SpectrumDigitizer:
    def analyze(self, img_path: str) -> Dict[str, Any]:
        if not cv2 or not np:
            return {"kind": "unknown", "x_unit": None, "y_unit": None, "peaks": [], "params": {}, "confidence": 0.0, "method": "stub"}
        img = cv2.imread(img_path)
        if img is None:
            # Fallback: Unicode path safe read
            try:
                data = np.fromfile(img_path, dtype=np.uint8)
                img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            except Exception:
                img = None
        if img is None:
            return {"kind": "unknown", "x_unit": None, "y_unit": None, "peaks": [], "params": {}, "confidence": 0.0, "method": "opencv_imread_failed", "path": img_path}
        # Stub processing (you can replace with real digitization later)
        return {"kind": "emission_or_absorption", "x_unit": "nm", "y_unit": "a.u.", "peaks": [], "params": {}, "confidence": 0.2, "method": "opencv_stub"}
