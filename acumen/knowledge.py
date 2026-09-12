from copy import deepcopy
import json
import math
from pathlib import Path

from .storage import atomic_write_json, read_json, utc_now, new_id
from .text import normalize_question, similarity
from .router import requires_fresh_data


def _text(value):
    return " ".join(str(value or "").split())


def _confidence(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.5
    return max(0.0, min(1.0, number)) if math.isfinite(number) else 0.5


def _merge_sources(*groups):
    result = []
    indexes = {}
    for group in groups:
        if isinstance(group, (str, dict)):
            group = [group]
        for source in group or []:
            if isinstance(source, str):
                source = source.strip()
                if not source:
                    continue
                key = ("url", source)
                source = {"url": source, "title": source}
            elif isinstance(source, dict):
                source = deepcopy(source)
                if isinstance(source.get("url"), str):
                    source["url"] = source["url"].strip()
                key = ("url", source["url"]) if source.get("url") else (
                    "source", json.dumps(source, sort_keys=True, ensure_ascii=False)
                )
            else:
                continue
            if key not in indexes:
                indexes[key] = len(result)
                result.append(source)
            elif isinstance(source, dict):
                index = indexes[key]
                if isinstance(result[index], str):
                    result[index] = source
                else:
                    for field, value in source.items():
                        if not result[index].get(field):
                            result[index][field] = value
    return result


def _merge_evidence(*groups):
    result = []
    indexes = {}
    for group in groups:
        if not isinstance(group, list):
            continue
        for evidence in group:
            if not isinstance(evidence, (str, dict)):
                continue
            evidence = deepcopy(evidence)
            if (
                isinstance(evidence, dict)
                and isinstance(evidence.get("text"), str)
                and isinstance(evidence.get("url"), str)
                and evidence["text"].strip()
                and evidence["url"].strip()
            ):
                evidence["url"] = evidence["url"].strip()
                key = ("passage", _text(evidence["text"]).casefold(), evidence["url"])
            else:
                key = ("evidence", json.dumps(evidence, sort_keys=True, ensure_ascii=False))
            if key not in indexes:
                indexes[key] = len(result)
                result.append(evidence)
            elif isinstance(evidence, dict):
                existing = result[indexes[key]]
                for field, value in evidence.items():
                    if field != "score" and not existing.get(field):
                        existing[field] = value
                try:
                    incoming_score = float(evidence.get("score"))
                except (TypeError, ValueError, OverflowError):
                    continue
                try:
                    existing_score = float(existing.get("score"))
                except (TypeError, ValueError, OverflowError):
                    existing_score = float("nan")
                if math.isfinite(incoming_score) and (
                    not math.isfinite(existing_score) or incoming_score > existing_score
                ):
                    existing["score"] = incoming_score
    return result


def clean_candidate(candidate):
    """Normalize a candidate without dropping its metadata or source evidence."""
    cleaned = deepcopy(candidate)
    cleaned["query"] = _text(candidate.get("query", ""))
    cleaned["answer"] = _text(candidate.get("answer", ""))
    cleaned["kind"] = _text(candidate.get("kind", "research")).casefold() or "research"
    cleaned["confidence"] = _confidence(candidate.get("confidence", 0.5))
    cleaned["sources"] = _merge_sources(candidate.get("sources", []))
    if "evidence" in candidate:
        cleaned["evidence"] = _merge_evidence(candidate["evidence"])
    return cleaned


def candidate_fingerprint(candidate):
    """Include the answer and kind so conflicting facts remain separate records."""
    kind = _text(candidate.get("kind", "research")).casefold() or "research"
    query = _text(candidate.get("query", ""))
    answer = _text(candidate.get("answer", ""))
    if kind != "math":
        query = normalize_question(query)
        answer = answer.casefold()
    return kind, query, answer


def merge_candidate(existing, incoming):
    """Merge corroboration while preserving the original identity and provenance."""
    merged = clean_candidate(existing)
    incoming = clean_candidate(incoming)
    merged["sources"] = _merge_sources(merged["sources"], incoming["sources"])
    merged["confidence"] = max(merged["confidence"], incoming["confidence"])
    if not incoming.get("learnable", True):
        merged["learnable"] = False
    if "evidence" in merged or "evidence" in incoming:
        merged["evidence"] = _merge_evidence(merged.get("evidence"), incoming.get("evidence"))
    return merged


def matching_answers(items, query):
    """Keep math case-sensitive and never match merely overlapping topics."""
    wanted = normalize_question(query)
    if not wanted or requires_fresh_data(query):
        return []
    return [item for item in items if item.get("answer") and (
        _text(item.get("query")) == _text(query) if item.get("kind") == "math"
        else normalize_question(item.get("query", "")) == wanted
    )]


def select_answer(items, query):
    """Abstain when stored versions disagree; usage is not proof of truth."""
    matches = matching_answers(items, query)
    answers = {
        _text(item["answer"]) if item.get("kind") == "math"
        else _text(item["answer"]).casefold() for item in matches
    }
    if len(answers) != 1:
        return None
    eligible = [item for item in matches if item.get("learnable", True)
                and _confidence(item.get("confidence", .5)) >= .5]
    return max(eligible, key=lambda item: _confidence(item.get("confidence", .5)), default=None)


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
        js = "window.ACUMEN_KNOWLEDGE = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"
        self.js_path.write_text(js, encoding="utf-8")

    def all(self):
        return self._load()["items"]

    def lookup(self, query):
        """Reuse an unambiguous answer to the same normalized question."""
        return select_answer(self.all(), query)

    def record_use(self, item_id):
        """Track actual retrieval without inflating confidence."""
        if not item_id:
            return False
        data = self._load()
        for item in data["items"]:
            if item.get("id") == item_id:
                item["use_count"] = int(item.get("use_count", 0) or 0) + 1
                item["last_used_at"] = utc_now()
                self._save(data)
                return True
        return False

    def add(self, candidate):
        return self.add_many([candidate])[0]

    def add_many(self, candidates):
        """Persist a batch with one read and one write; return one item per input."""
        candidates = [clean_candidate(candidate) for candidate in candidates]
        if not candidates:
            return []
        data = self._load()
        items = data["items"]
        by_fingerprint = {candidate_fingerprint(item): item for item in items}
        saved = []
        now = utc_now()
        for candidate in candidates:
            fingerprint = candidate_fingerprint(candidate)
            existing = by_fingerprint.get(fingerprint)
            if existing is not None:
                merged = merge_candidate(existing, candidate)
                merged["updated_at"] = now
                existing.clear()
                existing.update(merged)
                item = existing
            else:
                item = {
                    "id": new_id(),
                    "query": candidate["query"],
                    "answer": candidate["answer"],
                    "sources": candidate["sources"],
                    "kind": candidate["kind"],
                    "confidence": candidate["confidence"],
                    "use_count": 0,
                    "created_at": now,
                    "updated_at": now,
                }
                if "evidence" in candidate:
                    item["evidence"] = candidate["evidence"]
                if "learnable" in candidate:
                    item["learnable"] = candidate["learnable"]
                items.append(item)
                by_fingerprint[fingerprint] = item
            saved.append(item)
        self._save(data)
        return deepcopy(saved)

    def delete(self, item_id):
        data = self._load()
        original_count = len(data["items"])
        data["items"] = [item for item in data["items"] if item.get("id") != item_id]
        if len(data["items"]) == original_count:
            return False
        self._save(data)
        return True

    def search(self, query, limit=5):
        """Rank stored items by blended query similarity, best first."""
        matches = []
        for item in self.all():
            score = similarity(query, item.get("query", ""))
            if score >= .2:
                matches.append((score, item))
        matches.sort(key=lambda match: match[0], reverse=True)
        return [dict(item, score=round(score, 3)) for score, item in matches[:limit]]
