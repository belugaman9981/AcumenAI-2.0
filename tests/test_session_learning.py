from unittest.mock import patch

import pytest

from acumen.config import DEFAULTS
from acumen.knowledge import KnowledgeStore
from acumen.processor import TaskProcessor
from acumen.sessions import SessionStore


def candidate(query="Why is the sky blue?", answer="Air scatters blue light.", **extra):
    return {"query": query, "answer": answer, "kind": "research", **extra}


def test_session_merges_duplicate_learning_and_preserves_sources(tmp_path):
    sessions = SessionStore(tmp_path)
    sid = sessions.create()
    first = {"title": "First", "url": "https://example.org/first"}
    second = {"title": "Second", "url": "https://example.org/second"}
    sessions.add_candidate(sid, candidate(sources=[first], confidence=.6))
    sessions.add_candidate(sid, candidate(
        "  WHY  is the sky blue?  ", "Air  scatters blue light. ",
        sources=[second, first], confidence=.8,
    ))
    items = sessions.get(sid)["candidates"]
    assert len(items) == 1
    assert {s["url"] for s in items[0]["sources"]} == {first["url"], second["url"]}
    assert items[0]["confidence"] == .8
    assert items[0]["answer"] == "Air scatters blue light."
    with patch.object(sessions, "_write", wraps=sessions._write) as write:
        sessions.add_candidate(sid, items[0])
    write.assert_not_called()


@pytest.mark.parametrize("choice, expected", [(["s"], 3), (["r", "y", "n", "y"], 2)])
def test_session_saves_selected_learning_in_one_batch(tmp_path, choice, expected):
    sessions = SessionStore(tmp_path)
    store = KnowledgeStore(tmp_path)
    sid = sessions.create()
    for index in range(3):
        sessions.add_candidate(sid, candidate(f"Question {index}", f"Answer {index}"))
    with patch("builtins.input", side_effect=choice), patch.object(
        store, "_save", wraps=store._save,
    ) as save:
        sessions.finalize_interactive(sid, store)
    assert save.call_count == 1
    assert len(store.all()) == expected
    assert sessions.get(sid) is None


def test_failed_save_keeps_session_for_retry(tmp_path):
    sessions = SessionStore(tmp_path)
    store = KnowledgeStore(tmp_path)
    sid = sessions.create()
    sessions.add_candidate(sid, candidate())
    with patch("builtins.input", return_value="s"), patch.object(
        store, "add_many", side_effect=OSError("disk unavailable"),
    ), pytest.raises(OSError):
        sessions.finalize_interactive(sid, store)
    assert len(sessions.get(sid)["candidates"]) == 1


def test_sentence_evidence_survives_learning_and_save(tmp_path):
    processor = TaskProcessor(tmp_path, DEFAULTS)
    sid = processor.sessions.create()
    evidence = [{
        "text": "Air scatters blue light.",
        "url": "https://example.org/sky", "title": "Sky", "score": .8,
    }]
    result = {
        "ok": True, "answer": "Air scatters blue light.", "confidence": .7,
        "sources": [{"url": "https://example.org/sky", "title": "Sky"}],
        "evidence": evidence,
    }
    with patch.object(processor.researcher, "research", return_value=result):
        assert processor.process("research", {"query": "Why is the sky blue?"}, sid) == result
    pending = processor.sessions.get(sid)["candidates"]
    assert pending[0]["evidence"] == evidence
    assert processor.knowledge.all() == []
    processor.knowledge.add_many(pending)
    assert processor.knowledge.all()[0]["evidence"] == evidence
    with patch.object(processor.researcher, "research", side_effect=AssertionError("unexpected fetch")):
        recalled = processor.process("knowledge_query", {"query": "Why is the sky blue?"}, sid)
    assert recalled["from_knowledge"] is True
    assert recalled["evidence"] == evidence
    assert recalled["confidence"] == .7


def test_failed_research_does_not_create_learning(tmp_path):
    processor = TaskProcessor(tmp_path, DEFAULTS)
    sid = processor.sessions.create()
    with patch.object(processor.researcher, "research", return_value={"ok": False}):
        processor.process("research", {"query": "Unanswered question"}, sid)
    assert processor.sessions.get(sid)["candidates"] == []
