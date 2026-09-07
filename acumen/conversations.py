from __future__ import annotations
from pathlib import Path
import uuid
from .storage import JSONLStore, utc_now

class ConversationStore:
    def __init__(self, root: Path):
        self.store = JSONLStore(root / "conversations.jsonl")

    def add_turn(self, role: str, text: str, metadata: dict | None = None) -> dict:
        item = {
            "id": str(uuid.uuid4()),
            "role": role,
            "text": text,
            "created_at": utc_now(),
            "metadata": metadata or {},
        }
        self.store.append(item)
        return item

    def recent(self, limit: int = 20) -> list[dict]:
        return self.store.read_all()[-limit:]
