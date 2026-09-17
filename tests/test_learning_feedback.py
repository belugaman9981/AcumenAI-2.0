"""Keep session review decisions without turning them into permanent knowledge."""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import patch

import pytest

from acumen.knowledge import KnowledgeStore
from acumen.sessions import (
    DECLINED_LEARNING_LIMIT,
    PendingLearningChanged,
    SessionStore,
    candidate_review_id,
)


def candidate(query="Why is the sky blue?", answer="Air scatters blue light.", **extra):
    return {
        "query": query, "answer": answer, "kind": "research", "confidence": .8,
        "sources": [{"url": "https://example.org/sky", "title": "Sky"}],
        **extra,
    }


@pytest.fixture
def learning(tmp_path):
    sessions = SessionStore(tmp_path)
    return sessions, sessions.create(), KnowledgeStore(tmp_path)


def test_declined_answer_survives_process_restart_and_repeated_sources(tmp_path):
    """Exercise real persistence across separate Python processes."""
    script = """
import json
from pathlib import Path
import sys
from acumen.knowledge import KnowledgeStore
from acumen.sessions import SessionStore
root = Path(sys.argv[1])
sessions = SessionStore(root)
knowledge = KnowledgeStore(root)
candidate = {"query": "Why is the sky blue?", "answer": "Air scatters blue light.", "kind": "research"}
if len(sys.argv) == 2:
    sid = sessions.create()
    sessions.add_candidate(sid, candidate)
    assert sessions.resolve_pending(sid, "discard", knowledge) == 1
    print(sid)
else:
    sid = sys.argv[2]
    candidate.update(query="  WHY is the sky blue! ", answer="AIR  scatters blue light.",
                     confidence=.99, sources=[{"url": "https://example.org/new"}])
    before = sessions._path(sid).read_bytes()
    sessions.add_candidate(sid, candidate)
    assert sessions._path(sid).read_bytes() == before
    assert sessions.get(sid)["candidates"] == []
    assert knowledge.all() == []
    print("suppressed")
"""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TEMP=str(tmp_path), TMP=str(tmp_path))
    command = [sys.executable, "-B", "-c", script, str(tmp_path)]
    first = subprocess.run(command, capture_output=True, text=True, check=True, env=env,
                           cwd=Path(__file__).resolve().parents[1], timeout=30)
    second = subprocess.run(command + [first.stdout.strip()], capture_output=True, text=True,
                            check=True, env=env, cwd=Path(__file__).resolve().parents[1], timeout=30)
    assert second.stdout.strip() == "suppressed"


@pytest.mark.parametrize("change", [
    {"answer": "Shorter wavelengths scatter more strongly."},
    {"query": "Why is the ocean blue?"},
    {"kind": "explanation"},
])
def test_discard_keeps_different_answers_questions_and_kinds_eligible(learning, change):
    sessions, sid, knowledge = learning
    sessions.add_candidate(sid, candidate())
    sessions.resolve_pending(sid, "discard", knowledge)
    alternative = candidate(**change)
    sessions.add_candidate(sid, alternative)
    pending = sessions.get(sid)["candidates"]
    assert len(pending) == 1
    for field, value in change.items():
        assert pending[0][field] == value


@pytest.mark.parametrize("individual", [False, True])
def test_discard_preserves_saved_knowledge_and_other_pending_items(learning, individual):
    sessions, sid, knowledge = learning
    first = candidate()
    neighbor = candidate("What causes rain?", "Water droplets grow and fall.")
    knowledge.add(first)
    saved_before = knowledge.path.read_bytes()
    sessions.add_candidate(sid, first)
    sessions.add_candidate(sid, neighbor)
    originals = sessions.get(sid)["candidates"]
    item_id = candidate_review_id(originals[0]) if individual else None
    assert sessions.resolve_pending(sid, "discard", knowledge, item_id) == (1 if individual else 2)
    assert sessions.get(sid)["candidates"] == ([originals[1]] if individual else [])
    assert knowledge.path.read_bytes() == saved_before
    sessions.add_candidate(sid, first)
    assert sessions.get(sid)["candidates"] == ([originals[1]] if individual else [])


def test_feedback_is_isolated_to_one_session(learning):
    sessions, sid, knowledge = learning
    other = sessions.create()
    sessions.add_candidate(sid, candidate())
    sessions.resolve_pending(sid, "discard", knowledge)
    sessions.add_candidate(other, candidate())
    assert len(sessions.get(other)["candidates"]) == 1
    assert sessions.get(sid)["candidates"] == []
    assert "declined_fingerprints" not in sessions.get(other)


@pytest.mark.parametrize("finish", ["clear", "finalize"])
def test_feedback_expires_when_session_is_removed(learning, finish):
    sessions, sid, knowledge = learning
    sessions.add_candidate(sid, candidate())
    sessions.resolve_pending(sid, "discard", knowledge)
    if finish == "clear":
        sessions.clear(sid)
    else:
        sessions.finalize_interactive(sid, knowledge)
    assert sessions.get(sid) is None
    sessions.add_candidate(sid, candidate())
    assert len(sessions.get(sid)["candidates"]) == 1


@pytest.mark.parametrize("individual", [False, True])
def test_save_does_not_mark_candidates_declined(learning, individual):
    sessions, sid, knowledge = learning
    sessions.add_candidate(sid, candidate())
    original = sessions.get(sid)["candidates"][0]
    item_id = candidate_review_id(original) if individual else None
    assert sessions.resolve_pending(sid, "save", knowledge, item_id) == 1
    assert not sessions.get(sid).get("declined_fingerprints")
    sessions.add_candidate(sid, candidate())
    assert sessions.get(sid)["candidates"] == [original]
    assert len(knowledge.all()) == 1


def test_declined_feedback_stores_only_bounded_hashes(learning):
    sessions, sid, knowledge = learning
    for index in range(DECLINED_LEARNING_LIMIT + 1):
        sessions.add_candidate(sid, candidate(f"Private question {index}", f"Private answer {index}"))
    assert sessions.resolve_pending(sid, "discard", knowledge) == DECLINED_LEARNING_LIMIT + 1
    feedback = sessions.get(sid)["declined_fingerprints"]
    assert len(feedback) == DECLINED_LEARNING_LIMIT
    assert len(set(feedback)) == DECLINED_LEARNING_LIMIT
    assert all(re.fullmatch(r"[a-f0-9]{64}", digest) for digest in feedback)
    assert "Private" not in sessions._path(sid).read_text(encoding="utf-8")
    sessions.add_candidate(sid, candidate(
        f"Private question {DECLINED_LEARNING_LIMIT}", f"Private answer {DECLINED_LEARNING_LIMIT}"))
    assert sessions.get(sid)["candidates"] == []
    sessions.add_candidate(sid, candidate("Private question 0", "Private answer 0"))
    assert len(sessions.get(sid)["candidates"]) == 1
    sessions.resolve_pending(sid, "discard", knowledge)
    assert len(sessions.get(sid)["declined_fingerprints"]) == DECLINED_LEARNING_LIMIT


def test_stale_review_still_fails_without_changing_feedback(learning):
    sessions, sid, knowledge = learning
    sessions.add_candidate(sid, candidate())
    item_id = candidate_review_id(sessions.get(sid)["candidates"][0])
    sessions.resolve_pending(sid, "discard", knowledge, item_id)
    before = sessions._path(sid).read_bytes()
    with pytest.raises(PendingLearningChanged):
        sessions.resolve_pending(sid, "discard", knowledge, item_id)
    assert sessions._path(sid).read_bytes() == before
    with patch.object(sessions, "_write", wraps=sessions._write) as write:
        assert sessions.resolve_pending(sid, "discard", knowledge) == 0
    write.assert_not_called()


def test_existing_sessions_and_exact_repeats_need_no_extra_writes(learning):
    sessions, sid, _ = learning
    assert "declined_fingerprints" not in sessions.get(sid)
    sessions.add_candidate(sid, candidate())
    before = sessions._path(sid).read_bytes()
    with patch.object(sessions, "_write", wraps=sessions._write) as write:
        sessions.add_candidate(sid, candidate())
    write.assert_not_called()
    assert sessions._path(sid).read_bytes() == before


@pytest.mark.parametrize("operation", ["discard", "add", "merge"])
def test_failed_session_write_preserves_disk_and_loaded_data(learning, operation):
    sessions, sid, knowledge = learning
    sessions.add_candidate(sid, candidate())
    shared = sessions.get(sid)
    original = deepcopy(shared)
    before = sessions._path(sid).read_bytes()
    with patch.object(sessions, "get", return_value=shared), patch(
        "acumen.sessions.atomic_write_json", side_effect=OSError("disk unavailable")
    ), pytest.raises(OSError):
        if operation == "discard":
            sessions.resolve_pending(sid, "discard", knowledge)
        elif operation == "add":
            sessions.add_candidate(sid, candidate(answer="An alternative answer."))
        else:
            sessions.add_candidate(sid, candidate(sources=[{"url": "https://example.org/new"}]))
    assert shared == original
    assert sessions._path(sid).read_bytes() == before
    assert knowledge.all() == []
    assert "declined_fingerprints" not in json.loads(before)
