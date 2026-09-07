from __future__ import annotations
from pathlib import Path
import math
import re
import uuid
from collections import Counter
from .storage import JSONLStore, utc_now

TOKEN_RE = re.compile(r"[A-Za-z0-9_'-]+", re.UNICODE)

def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]

def cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0

class MemoryStore:
    def __init__(self, root: Path):
        self.store = JSONLStore(root / "memories.jsonl")

    def add(self, text: str, kind: str = "semantic", source: str = "user",
            confidence: float = 0.75, metadata: dict | None = None) -> dict:
        item = {
            "id": str(uuid.uuid4()),
            "text": text.strip(),
            "kind": kind,
            "source": source,
            "confidence": float(confidence),
            "created_at": utc_now(),
            "last_used_at": None,
            "use_count": 0,
            "metadata": metadata or {},
        }
        self.store.append(item)
        return item

    def all(self) -> list[dict]:
        return self.store.read_all()

    def delete(self, memory_id: str) -> bool:
        items = self.all()
        kept = [m for m in items if m.get("id") != memory_id]
        if len(kept) == len(items):
            return False
        self.store.rewrite(kept)
        return True

    def search(self, query: str, limit: int = 8, min_score: float = 0.05) -> list[dict]:
        qv = Counter(tokenize(query))
        scored = []
        for m in self.all():
            mv = Counter(tokenize(m.get("text", "")))
            semantic = cosine(qv, mv)
            confidence = float(m.get("confidence", 0.5))
            score = semantic * (0.7 + 0.3 * confidence)
            if score >= min_score:
                scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{**m, "score": round(score, 4)} for score, m in scored[:limit]]

    def touch(self, ids: list[str]) -> None:
        if not ids:
            return
        items = self.all()
        changed = False
        for m in items:
            if m.get("id") in ids:
                m["use_count"] = int(m.get("use_count", 0)) + 1
                m["last_used_at"] = utc_now()
                changed = True
        if changed:
            self.store.rewrite(items)
