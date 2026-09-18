from pathlib import Path
from datetime import datetime, timezone
import json
import time
import uuid

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def _replace_with_retry(source: Path, target: Path):
    """Allow short Windows sharing locks without sacrificing atomic writes."""
    delays = (0.02, 0.05, 0.1, 0.2)
    for attempt in range(len(delays) + 1):
        try:
            source.replace(target)
            return
        except PermissionError as error:
            if getattr(error, "winerror", None) not in {5, 32, 33} or attempt == len(delays):
                raise
            time.sleep(delays[attempt])


def atomic_write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    _replace_with_retry(tmp, path)

def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def new_id():
    return str(uuid.uuid4())


class JSONLStore:
    """Append-only JSON Lines store with atomic full rewrites."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, item):
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        return item

    def read_all(self):
        if not self.path.exists():
            return []
        items = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return items

    def write_all(self, items):
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        _replace_with_retry(tmp, self.path)
        return items
