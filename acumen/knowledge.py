from __future__ import annotations
from pathlib import Path
import hashlib
import re
from .memory import MemoryStore

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

class KnowledgeIngestor:
    def __init__(self, memory: MemoryStore):
        self.memory = memory

    def ingest_text(self, text: str, source: str = "manual") -> list[dict]:
        chunks = []
        cleaned = " ".join(text.split())
        for sentence in SENTENCE_SPLIT.split(cleaned):
            sentence = sentence.strip()
            if len(sentence) < 12:
                continue
            digest = hashlib.sha256(sentence.encode("utf-8")).hexdigest()[:16]
            item = self.memory.add(
                sentence,
                kind="knowledge",
                source=source,
                confidence=0.8,
                metadata={"digest": digest},
            )
            chunks.append(item)
        return chunks

    def ingest_file(self, path: str) -> list[dict]:
        p = Path(path)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(path)
        if p.suffix.lower() not in {".txt", ".md", ".py", ".json", ".csv", ".yaml", ".yml"}:
            raise ValueError("v0.1 ingests text-like files only.")
        text = p.read_text(encoding="utf-8", errors="ignore")
        return self.ingest_text(text, source=f"file:{p}")
