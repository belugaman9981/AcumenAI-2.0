from pathlib import Path
import uuid
from .storage import JSONLStore, utc_now
from .text import cosine_text

class MemoryStore:
    def __init__(self, root: Path):
        self.store = JSONLStore(root / "memories.jsonl")

    def add(self, text, kind="episodic", source="conversation", confidence=0.5, metadata=None):
        item = {
            "id": str(uuid.uuid4()),
            "text": text.strip(),
            "kind": kind,
            "source": source,
            "confidence": float(confidence),
            "created_at": utc_now(),
            "use_count": 0,
            "metadata": metadata or {},
        }
        self.store.append(item)
        return item

    def all(self):
        return self.store.read_all()

    def search(self, query, limit=8, min_score=0.05):
        scored = []
        for m in self.all():
            score = cosine_text(query, m.get("text", "")) * float(m.get("confidence", 0.5))
            if score >= min_score:
                scored.append(({**m, "score": round(score, 4)}, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in scored[:limit]]
