import json
from unittest.mock import patch

from acumen.knowledge import (
    KnowledgeStore,
    candidate_fingerprint,
    clean_candidate,
    merge_candidate,
)


def test_batch_reads_and_writes_once_and_updates_both_exports(tmp_path):
    store = KnowledgeStore(tmp_path)
    candidates = [
        {"query": f"Question {index}", "answer": f"Answer {index}"}
        for index in range(50)
    ]
    with patch.object(store, "_load", wraps=store._load) as read:
        with patch.object(store, "_save", wraps=store._save) as write:
            saved = store.add_many(iter(candidates))
    assert read.call_count == 1
    assert write.call_count == 1
    assert len(saved) == 50
    data = json.loads(store.path.read_text(encoding="utf-8"))
    javascript = store.js_path.read_text(encoding="utf-8")
    assert json.loads(javascript.removeprefix("window.ACUMEN_KNOWLEDGE = ").rstrip(";\n")) == data
    assert len(data["items"]) == 50


def test_batch_duplicates_merge_sources_and_evidence_without_losing_identity(tmp_path):
    store = KnowledgeStore(tmp_path)
    old = store.add({
        "query": "Where is Ottawa?",
        "answer": "Ottawa is in Canada.",
        "sources": [{"url": "https://one.example", "title": "Original title"}],
        "confidence": 0.8,
        "evidence": [{"text": "Ottawa is in Canada.", "url": "https://one.example"}],
    })
    saved = store.add_many([
        {
            "query": " WHERE  is Ottawa? ",
            "answer": "Ottawa is in\nCanada. ",
            "sources": [{"url": "https://two.example", "title": "Second source"}],
            "confidence": 0.4,
            "evidence": [{"text": "Ottawa is in Canada.", "url": "https://two.example"}],
        },
        {
            "query": "where is ottawa?",
            "answer": "OTTAWA IS IN CANADA.",
            "sources": [{"url": "https://one.example", "title": "Later title", "publisher": "Publisher"}],
            "confidence": 0.9,
        },
    ])
    assert len(store.all()) == 1
    assert [item["id"] for item in saved] == [old["id"], old["id"]]
    item = store.all()[0]
    assert item["created_at"] == old["created_at"]
    assert item["query"] == "Where is Ottawa?"
    assert item["confidence"] == 0.9
    assert item["sources"] == [
        {"url": "https://one.example", "title": "Original title", "publisher": "Publisher"},
        {"url": "https://two.example", "title": "Second source"},
    ]
    assert len(item["evidence"]) == 2


def test_conflicting_answers_and_case_sensitive_math_remain_separate(tmp_path):
    store = KnowledgeStore(tmp_path)
    saved = store.add_many([
        {"query": "A question", "answer": "First answer"},
        {"query": "a question", "answer": "Different answer"},
        {"kind": "math", "query": "solve x + 1", "answer": "x = 1"},
        {"kind": "math", "query": "solve X + 1", "answer": "X = 1"},
        {"kind": "math", "query": "solve x + 1", "answer": "X = 1"},
    ])
    assert len({item["id"] for item in saved}) == 5
    assert len(store.all()) == 5


def test_single_add_uses_batch_and_empty_batch_does_no_io(tmp_path):
    store = KnowledgeStore(tmp_path)
    candidate = {"query": "Question", "answer": "Answer"}
    with patch.object(store, "add_many", wraps=store.add_many) as batch:
        saved = store.add(candidate)
    batch.assert_called_once_with([candidate])
    assert saved["query"] == "Question"
    with patch.object(store, "_load", wraps=store._load) as read:
        with patch.object(store, "_save", wraps=store._save) as write:
            assert store.add_many([]) == []
    read.assert_not_called()
    write.assert_not_called()


def test_helpers_leave_input_metadata_independent_and_do_not_invent_evidence():
    old = {
        "id": "old-id", "created_at": "original", "query": "  A  question ",
        "answer": " Some  answer ", "sources": [" https://one.example "],
        "confidence": "0.8", "review": {"status": "pending"},
    }
    new = {"query": "a question", "answer": "some answer", "sources": ["https://two.example"]}
    merged = merge_candidate(old, new)
    assert candidate_fingerprint(old) == candidate_fingerprint(new)
    assert merged["query"] == "A question"
    assert merged["id"] == "old-id"
    assert merged["created_at"] == "original"
    assert [source["url"] for source in merged["sources"]] == [
        "https://one.example", "https://two.example"
    ]
    assert all(isinstance(source, dict) and source.get("title") for source in merged["sources"])
    assert "evidence" not in merged
    merged["review"]["status"] = "changed"
    assert old["review"]["status"] == "pending"
    assert old["sources"] == [" https://one.example "]


def test_confidence_is_finite_and_bounded():
    assert clean_candidate({"confidence": float("nan")})["confidence"] == 0.5
    assert clean_candidate({"confidence": "invalid"})["confidence"] == 0.5
    assert clean_candidate({"confidence": 2})["confidence"] == 1.0
    assert clean_candidate({"confidence": -1})["confidence"] == 0.0


def test_other_store_instances_see_writes_and_deletions(tmp_path):
    first = KnowledgeStore(tmp_path)
    second = KnowledgeStore(tmp_path)
    assert second.all() == []
    saved = first.add({"query": "Ottawa", "answer": "Canada"})
    assert second.all()[0]["id"] == saved["id"]
    assert second.delete(saved["id"])
    assert first.all() == []


def test_repeated_evidence_merges_by_passage_and_url_retaining_best_score():
    old = {
        "query": "Where is Ottawa?",
        "answer": "Ottawa is in Canada.",
        "evidence": [{
            "text": "Ottawa is in Canada.",
            "url": "https://one.example",
            "score": 0.6,
            "title": "Original title",
        }],
    }
    incoming = {
        "query": "Where is Ottawa?",
        "answer": "Ottawa is in Canada.",
        "evidence": [{
            "text": " OTTAWA  is in\nCanada. ",
            "url": " https://one.example ",
            "score": 0.8,
            "title": "New title",
            "publisher": "Publisher",
        }],
    }
    merged = merge_candidate(old, incoming)
    assert merged["evidence"] == [{
        "text": "Ottawa is in Canada.",
        "url": "https://one.example",
        "score": 0.8,
        "title": "Original title",
        "publisher": "Publisher",
    }]
    assert merge_candidate(merged, old)["evidence"] == merged["evidence"]
    assert old["evidence"][0]["score"] == 0.6
