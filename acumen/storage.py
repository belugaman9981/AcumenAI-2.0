from __future__ import annotations
from pathlib import Path
import json
import threading
from datetime import datetime, timezone

class JSONLStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.touch()

    def append(self, item: dict) -> None:
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def read_all(self) -> list[dict]:
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

    def rewrite(self, items: list[dict]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with self._lock, tmp.open("w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        tmp.replace(self.path)

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
