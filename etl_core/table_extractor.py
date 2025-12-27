import json, csv
from pathlib import Path
from typing import List, Dict, Any

def _safe_import(name):
    try:
        return __import__(name)
    except Exception:
        return None

camelot = _safe_import("camelot")
pdfplumber = _safe_import("pdfplumber")

def extract_tables(pdf_path: str, out_dir: str) -> List[Dict[str, Any]]:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    metas = []
    if camelot:
        try:
            tables = camelot.read_pdf(pdf_path, pages="all", flavor="lattice")
            for i, t in enumerate(tables, start=1):
                csv_path = Path(out_dir) / f"table_{i}.csv"
                t.to_csv(str(csv_path))
                metas.append({"id": i, "method": "camelot_lattice", "csv_path": str(csv_path)})
        except Exception:
            pass
        try:
            base = len(metas)
            tables = camelot.read_pdf(pdf_path, pages="all", flavor="stream")
            for j, t in enumerate(tables, start=1):
                csv_path = Path(out_dir) / f"table_{base+j}.csv"
                t.to_csv(str(csv_path))
                metas.append({"id": base+j, "method": "camelot_stream", "csv_path": str(csv_path)})
        except Exception:
            pass

    if not metas and pdfplumber:
        with pdfplumber.open(pdf_path) as pdf:
            tid = 1
            for pidx, page in enumerate(pdf.pages, start=1):
                try:
                    tables = page.extract_tables() or []
                    for t in tables:
                        csv_path = Path(out_dir) / f"table_{tid}.csv"
                        with open(csv_path, "w", newline="", encoding="utf-8") as f:
                            writer = csv.writer(f)
                            for row in t:
                                writer.writerow(row)
                        metas.append({"id": tid, "method": "pdfplumber", "page": pidx, "csv_path": str(csv_path)})
                        tid += 1
                except Exception:
                    continue
    meta_path = Path(out_dir) / "tables_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metas, f, ensure_ascii=False, indent=2)
    return metas
