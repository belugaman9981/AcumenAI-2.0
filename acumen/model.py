from __future__ import annotations
from abc import ABC, abstractmethod

class ModelBackend(ABC):
    @abstractmethod
    def generate(self, user_input: str, memories: list[dict], recent_turns: list[dict]) -> str:
        raise NotImplementedError

class RuleBasedBackend(ModelBackend):
    def generate(self, user_input: str, memories: list[dict], recent_turns: list[dict]) -> str:
        if memories:
            lines = [m["text"] for m in memories[:4]]
            joined = "\n- ".join(lines)
            return (
                "I do not have a full language model connected yet, but I found relevant memory:\n"
                f"- {joined}\n\n"
                "You can connect a local LLM backend later for natural-language reasoning."
            )
        return (
            "Acumen's core is running, but no local LLM backend is connected yet. "
            "I can still store/retrieve memory, ingest text, and use tools. "
            "Use /remember, /learn, /ingest, /memories, or /calc."
        )
