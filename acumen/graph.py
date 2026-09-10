from pathlib import Path
import uuid
from .storage import JSONLStore, utc_now

class KnowledgeGraph:
    def __init__(self, root: Path):
        self.store = JSONLStore(root / "facts.jsonl")

    def all(self):
        return self.store.read_all()

    def add_verified(self, subject, relation, obj, confidence, evidence, source="web_verifier"):
        facts = self.all()
        for fact in facts:
            if fact["subject"] == subject and fact["relation"] == relation and fact["object"] == obj:
                fact["confidence"] = max(float(fact.get("confidence", 0)), float(confidence))
                fact["status"] = "verified"
                fact["evidence"] = evidence
                fact["updated_at"] = utc_now()
                self.store.rewrite(facts)
                return fact

        fact = {
            "id": str(uuid.uuid4()),
            "subject": subject,
            "relation": relation,
            "object": obj,
            "confidence": float(confidence),
            "status": "verified",
            "source": source,
            "evidence": evidence,
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        self.store.append(fact)
        return fact

    def query(self, subject=None, relation=None, obj=None):
        out = []
        for f in self.all():
            if f.get("status") != "verified":
                continue
            if subject is not None and f["subject"] != subject:
                continue
            if relation is not None and f["relation"] != relation:
                continue
            if obj is not None and f["object"] != obj:
                continue
            out.append(f)
        return out
