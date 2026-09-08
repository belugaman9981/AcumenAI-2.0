from pathlib import Path
import re

SPLIT = re.compile(r"(?<=[.!?])\s+")

class KnowledgeIngestor:
    def __init__(self, learner):
        self.learner = learner

    def ingest_text(self, text, source="manual"):
        results = []
        cleaned = " ".join(text.split())
        for sentence in SPLIT.split(cleaned):
            sentence = sentence.strip()
            if len(sentence) < 8:
                continue
            triples, facts = self.learner.learn(sentence, source=source, confidence=0.8)
            results.append((sentence, triples, facts))
        return results

    def ingest_file(self, path):
        p = Path(path)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(path)
        if p.suffix.lower() not in {".txt",".md",".py",".json",".csv",".yaml",".yml"}:
            raise ValueError("v0.2.2 currently ingests text-like files only.")
        return self.ingest_text(
            p.read_text(encoding="utf-8", errors="ignore"),
            source=f"file:{p}"
        )
