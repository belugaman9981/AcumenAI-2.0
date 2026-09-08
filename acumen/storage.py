from pathlib import Path
from datetime import datetime, timezone
import json
import threading

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def atomic_json_write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

class JSONLStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self.path.touch()

    def append(self, item):
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def read_all(self):
        items = []
        if not self.path.exists():
            return items
        with self._lock, self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return items

    def rewrite(self, items):
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with self._lock, tmp.open("w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        tmp.replace(self.path)
