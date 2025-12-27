import hashlib, json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

@dataclass
class Provenance:
    pdf_path: str
    page: int | None
    bbox: list[float] | None
    method: str
    asset_path: str | None
    caption: str | None
    snippet: str | None
    confidence: float | None
    sha256: str | None

    def to_json(self):
        d = asdict(self)
        d["timestamp"] = datetime.utcnow().isoformat()
        return d

def sha256_of_file(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None

def append_ledger(ledger_path: str, record: dict):
    Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
