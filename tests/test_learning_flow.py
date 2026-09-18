"""Exercise evidence, freshness and feedback through the actual chat/API flow."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from acumen.bridge import make_app
from acumen.config import DEFAULTS
from acumen.learning_review import adds_evidence


QUESTION = "Why is the sky blue?"
ANSWER = "The sky is blue because air scatters blue light."
HEADERS = {"X-Acumen-Token": "learning-flow-token"}


def supported(answer=ANSWER, url="https://example.org/sky", **extra):
    return {"ok": True, "answer": answer, "confidence": .7,
            "sources": [{"url": url, "title": "Sky"}],
            "evidence": [{"url": url, "text": answer, "kind": "page"}], **extra}


@pytest.fixture
def flow(tmp_path):
    config = deepcopy(DEFAULTS)
    config["web"]["pairing_token"] = HEADERS["X-Acumen-Token"]
    app = make_app(tmp_path, config)
    app.testing = True
    client = app.extensions["acumen_client"]
    yield app.test_client(), client
    client.local_processor.close()


def ask(api, question=QUESTION):
    response = api.post("/api/chat", json={"message": question}, headers=HEADERS)
    assert response.status_code == 200
    return response.json["reply"]


def pending(api):
    response = api.get("/api/session", headers=HEADERS)
    assert response.status_code == 200
    return response.json["candidates"]


def review(api, action, item):
    response = api.post("/api/session/learning", headers=HEADERS,
                        json={"action": action, "item_id": item["review_id"]})
    assert response.status_code == 200
    assert response.json["count"] == 1


@pytest.mark.parametrize("overrides", [
    {"evidence": []}, {"confidence": True},
    {"evidence": [{"url": "https://example.org/sky", "text": ANSWER, "kind": "snippet"}]},
    {"answer": ANSWER + " An unsupported extra claim."},
])
def test_displayable_result_without_full_page_support_is_not_learned(flow, overrides):
    api, client = flow
    with patch.object(client.local_processor.researcher, "research", return_value={**supported(), **overrides}):
        assert ANSWER in ask(api)
    assert pending(api) == []
    assert client.knowledge.all() == []


def test_supported_answer_reuses_then_skips_saved_duplicates_and_merges_new_evidence(flow):
    api, client = flow
    processor = client.local_processor
    with patch.object(processor.researcher, "research", return_value=supported()) as research:
        assert ANSWER in ask(api)
        assert ANSWER in ask(api, "Why's the sky blue?")
        assert research.call_count == 1
        item = pending(api)[0]
        assert item["learning_review"]["status"] == "new"
        assert item["learning_review"]["source_count"] == 1
        assert item["researched_at"]
        review(api, "save", item)
        processor.process("research", {"query": QUESTION}, client.session_id)
        assert pending(api) == []
    previous = client.knowledge.all()[0]
    assert previous["confidence"] == .7
    newer = supported(url="https://second.example/sky")
    with patch.object(processor.researcher, "research", return_value=newer):
        processor.process("research", {"query": QUESTION}, client.session_id)
    item = pending(api)[0]
    assert item["learning_review"]["status"] == "evidence_update"
    review(api, "save", item)
    saved = client.knowledge.all()
    assert len(saved) == 1 and saved[0]["id"] == previous["id"]
    assert len(saved[0]["evidence"]) == len(saved[0]["sources"]) == 2
    assert saved[0]["confidence"] == .7


def test_discard_suppresses_same_answer_but_a_different_answer_can_be_reviewed(flow):
    api, client = flow
    with patch.object(client.local_processor.researcher, "research", return_value=supported()) as research:
        ask(api)
        review(api, "discard", pending(api)[0])
        ask(api)
        assert research.call_count == 2
        assert pending(api) == []
    alternative = "The sky appears blue because short wavelengths scatter strongly."
    with patch.object(client.local_processor.researcher, "research", return_value=supported(alternative)):
        ask(api)
    assert [item["answer"] for item in pending(api)] == [alternative]
    assert client.knowledge.all() == []


def test_old_saved_answer_is_researched_again_and_needs_review_to_refresh_its_date(flow):
    api, client = flow
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    saved = client.knowledge.add({"query": QUESTION, "kind": "research", "researched_at": old, **supported()})
    with patch.object(client.local_processor.researcher, "research", return_value=supported()) as research:
        ask(api)
        research.assert_called_once_with(QUESTION)
    item = pending(api)[0]
    assert item["learning_review"]["status"] == "rechecked"
    assert client.knowledge.all()[0]["researched_at"] == old
    review(api, "save", item)
    refreshed = client.knowledge.all()[0]
    assert refreshed["id"] == saved["id"]
    assert refreshed["researched_at"] != old
    with patch.object(client.local_processor.researcher, "research", side_effect=AssertionError("unexpected fetch")):
        assert ANSWER in ask(api)


@pytest.mark.parametrize("days,research_calls", [(1, 1), (60, 0)])
def test_processor_obeys_configured_recheck_age(flow, days, research_calls):
    api, client = flow
    client.config["learning"]["recheck_after_days"] = days
    old = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    client.knowledge.add({"query": QUESTION, "kind": "research", "researched_at": old, **supported()})
    with patch.object(client.local_processor.researcher, "research", return_value=supported()) as research:
        assert ANSWER in ask(api)
        assert research.call_count == research_calls


def test_differing_answer_is_explained_and_does_not_silently_replace_saved_version(flow):
    api, client = flow
    alternative = "The sky appears blue because short wavelengths scatter strongly."
    old = client.knowledge.add({"query": QUESTION, "kind": "research", **supported(alternative)})
    with patch.object(client.local_processor.researcher, "research", return_value=supported()):
        client.local_processor.process("research", {"query": QUESTION}, client.session_id)
    item = pending(api)[0]
    assert item["learning_review"]["status"] == "conflict"
    assert item["learning_review"]["other_answers"] == [alternative]
    review(api, "save", item)
    assert len(client.knowledge.all()) == 2
    assert any(entry["id"] == old["id"] for entry in client.knowledge.all())
    with patch.object(client.local_processor.researcher, "research", return_value=supported()) as research:
        ask(api)
        research.assert_called_once()


def test_uncited_extra_passage_does_not_look_like_new_support():
    saved = {"kind": "research", "query": QUESTION, **supported()}
    candidate = deepcopy(saved)
    candidate["evidence"].append({"text": ANSWER, "url": "https://uncited.example/sky", "kind": "page"})
    assert not adds_evidence(candidate, [saved])


def test_word_fragment_does_not_look_like_new_support():
    saved = {"kind": "research", "query": QUESTION, **supported()}
    candidate = deepcopy(saved)
    candidate["evidence"].append({"text": "scatter", "url": "https://example.org/sky", "kind": "page"})
    assert not adds_evidence(candidate, [saved])
