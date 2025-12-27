from typing import List, Dict, Any, Tuple
import pandas as pd
from pathlib import Path
import json

PRIORITY = ["table", "spectrum_digitize", "figure_ocr", "text", "llm"]

def choose_value(candidates: List[Dict[str, Any]]) -> Tuple[Any, List[Dict[str, Any]]]:
    cs = sorted(candidates, key=lambda c: (PRIORITY.index(c.get("method","llm")) if c.get("method") in PRIORITY else 99,
                                           -(c.get("confidence") or 0)))
    best = cs[0]
    return best.get("value"), cs

def merge_records(text_json_path: str, table_records: List[Dict[str, Any]], spectrum_records: List[Dict[str, Any]], out_csv: str):
    main = {}
    if Path(text_json_path).exists():
        try:
            data = json.loads(Path(text_json_path).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                payload = data.get("data") or {}
                if isinstance(payload, dict):
                    main.update(payload)
        except Exception:
            pass
    df = pd.DataFrame([main]) if main else pd.DataFrame()
    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    if not df.empty:
        df.to_csv(out_csv, index=False)
    else:
        pd.DataFrame({"_empty": [True]}).to_csv(out_csv, index=False)
    return out_csv
