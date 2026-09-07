from __future__ import annotations
import re
from .memory import MemoryStore

QUESTION_RE = re.compile(r"^\s*(who|what|where|when|why|how|is|are|do|does|did|can|could|would|should)\b", re.I)

class Learner:
    def __init__(self, memory: MemoryStore):
        self.memory = memory

    def maybe_learn_user_statement(self, text: str) -> dict | None:
        t = text.strip()
        if len(t) < 12:
            return None
        if QUESTION_RE.match(t) or t.endswith("?") or t.startswith("/"):
            return None
        return self.memory.add(
            t,
            kind="episodic",
            source="conversation",
            confidence=0.55,
            metadata={"auto": True},
        )

    def reflect(self, user_input: str, response: str, used_memories: list[dict]) -> None:
        # v0.1 reflection is deliberately conservative.
        # It reinforces memory through usage rather than inventing new facts.
        self.memory.touch([m["id"] for m in used_memories])
