from pathlib import Path
import uuid
from .storage import JSONLStore, utc_now

class PatternStore:
    def __init__(self, root: Path):
        self.store = JSONLStore(root / "patterns.jsonl")

    def record(self, input_pattern, intent, success=True):
        item = {
            "id": str(uuid.uuid4()),
            "input_pattern": input_pattern,
            "intent": intent,
            "success": bool(success),
            "created_at": utc_now(),
        }
        self.store.append(item)
        return item

    def all(self):
        return self.store.read_all()
