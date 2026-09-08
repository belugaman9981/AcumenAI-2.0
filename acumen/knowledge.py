from pathlib import Path
from .storage import atomic_write_json, read_json, utc_now, new_id
import re

def _terms(text):
    return set(re.findall(r"[a-z0-9'-]+", text.lower()))

class KnowledgeStore:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "knowledge.json"
        self.js_path = root / "knowledge.js"
        root.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({"version": 1, "items": []})

    def _load(self):
        return read_json(self.path, {"version": 1, "items": []})

    def _save(self, data):
        atomic_write_json(self.path, data)
        # Browser-readable export. This stays local unless the user deliberately publishes it.
        js = "window.ACUMEN_KNOWLEDGE = " + __import__("json").dumps(
            data, ensure_ascii=False, indent=2
        ) + ";\n"
        self.js_path.write_text(js, encoding="utf-8")

    def all(self):
        return self._load()["items"]

    def add(self, candidate):
        data = self._load()
        fingerprint = (
            candidate.get("query", "").strip().lower(),
            candidate.get("answer", "").strip().lower(),
        )
        for item in data["items"]:
            if (
                item.get("query", "").strip().lower(),
                item.get("answer", "").strip().lower(),
            ) == fingerprint:
                item["updated_at"] = utc_now()
                item["sources"] = candidate.get("sources", item.get("sources", []))
                self._save(data)
                return item

        item = {
            "id": new_id(),
            "query": candidate.get("query", ""),
            "answer": candidate.get("answer", ""),
            "sources": candidate.get("sources", []),
            "kind": candidate.get("kind", "research"),
            "confidence": float(candidate.get("confidence", 0.5)),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        data["items"].append(item)
        self._save(data)
        return item

    def delete(self, item_id):
        data = self._load()
        before = len(data["items"])
        data["items"] = [x for x in data["items"] if x.get("id") != item_id]
        if len(data["items"]) == before:
            return False
        self._save(data)
        return True

    def search(self, query, limit=5):
        q = _terms(query)
        ranked = []
        for item in self.all():
            hay = _terms(item.get("query", "") + " " + item.get("answer", ""))
            if not q or not hay:
                score = 0
            else:
                score = len(q & hay) / max(1, len(q))
            if score:
                ranked.append((score, item))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [dict(item, score=round(score, 3)) for score, item in ranked[:limit]]
