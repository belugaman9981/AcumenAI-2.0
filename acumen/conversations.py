from pathlib import Path
import uuid
from .storage import JSONLStore, utc_now

class ConversationStore:
    def __init__(self, root: Path):
        self.store = JSONLStore(root / "conversations.jsonl")

    def add(self, role, text, metadata=None):
        item = {
            "id": str(uuid.uuid4()),
            "role": role,
            "text": text,
            "created_at": utc_now(),
            "metadata": metadata or {},
        }
        self.store.append(item)
        return item

    def recent(self, limit=20):
        return self.store.read_all()[-limit:]
