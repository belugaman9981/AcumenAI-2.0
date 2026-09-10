from pathlib import Path
from datetime import datetime, timezone
import json
import uuid

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def atomic_write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def new_id():
    return str(uuid.uuid4())
