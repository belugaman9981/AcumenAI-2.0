"""Review one exact pending learning revision without touching its neighbors."""
from copy import deepcopy
from unittest.mock import patch

import pytest

from acumen.bridge import make_app
from acumen.config import DEFAULTS
from acumen.knowledge import KnowledgeStore
from acumen.sessions import candidate_review_id


HEADERS = {"X-Acumen-Token": "individual-learning-test-token"}


@pytest.fixture
def bridge(tmp_path):
    config = deepcopy(DEFAULTS)
    config["web"]["pairing_token"] = HEADERS["X-Acumen-Token"]
    app = make_app(tmp_path, config)
    app.testing = True
    client = app.extensions["acumen_client"]
    yield app.test_client(), client
    client.local_processor.close()


def add_candidates(client, count=3):
    for index in range(count):
        client.session_store.add_candidate(client.session_id, {
            "query": f"Question {index}", "answer": f"Answer {index}",
            "kind": "research", "confidence": .8,
            "sources": [{"title": f"Source {index}", "url": f"https://example.org/{index}"}],
            "evidence": [{"text": f"Answer {index}", "url": f"https://example.org/{index}", "score": .8}],
        })
    return client.session_store.get(client.session_id)["candidates"]


def pending(api):
    response = api.get("/api/session", headers=HEADERS)
    assert response.status_code == 200
    return response.json["candidates"]


def review(api, action, item_id):
    return api.post("/api/session/learning", json={"action": action, "item_id": item_id}, headers=HEADERS)


def test_review_ids_are_stable_and_do_not_change_stored_candidates(bridge):
    api, client = bridge
    stored = add_candidates(client)
    session_path = client.session_store._path(client.session_id)
    before = session_path.read_bytes()
    exposed = pending(api)
    assert pending(api) == exposed
    assert len({item["review_id"] for item in exposed}) == len(stored)
    for item, original in zip(exposed, stored):
        assert item.pop("review_id") == candidate_review_id(original)
        assert item.pop("learning_review")["label"]
        assert item == original
        assert "review_id" not in original
    assert session_path.read_bytes() == before


def test_save_and_discard_individual_items_keep_other_candidates_and_evidence(bridge):
    api, client = bridge
    stored = add_candidates(client)
    exposed = pending(api)

    saved = review(api, "save", exposed[1]["review_id"])
    assert saved.status_code == 200
    assert saved.json == {"ok": True, "count": 1, "answer": "Saved 1 learning item(s)."}
    assert client.session_store.get(client.session_id)["candidates"] == [stored[0], stored[2]]
    permanent = client.knowledge.all()
    assert len(permanent) == 1
    for field in ("query", "answer", "sources", "evidence", "confidence"):
        assert permanent[0][field] == stored[1][field]

    # IDs address the same item even after the list has shifted twice.
    discarded = review(api, "discard", exposed[0]["review_id"])
    assert discarded.status_code == 200
    assert discarded.json["count"] == 1
    assert client.session_store.get(client.session_id)["candidates"] == [stored[2]]
    assert client.knowledge.all() == permanent
    last = review(api, "save", exposed[2]["review_id"])
    assert last.status_code == 200
    assert pending(api) == []
    assert {item["query"] for item in client.knowledge.all()} == {"Question 1", "Question 2"}


@pytest.mark.parametrize("action", ["save", "discard"])
def test_changed_evidence_rejects_stale_review_without_mutation(bridge, action):
    api, client = bridge
    originals = add_candidates(client)
    stale_id = pending(api)[1]["review_id"]
    revised = deepcopy(originals[1])
    revised["evidence"].append({"text": "Additional support", "url": "https://example.org/new", "score": .9})
    client.session_store.add_candidate(client.session_id, revised)
    before = client.session_store.get(client.session_id)
    knowledge_before = client.knowledge.all()
    current_id = pending(api)[1]["review_id"]
    assert current_id != stale_id

    response = review(api, action, stale_id)
    assert response.status_code == 409
    assert "changed" in response.json["error"]
    assert client.session_store.get(client.session_id) == before
    assert client.knowledge.all() == knowledge_before

    assert review(api, action, current_id).status_code == 200
    assert client.session_store.get(client.session_id)["candidates"] == [originals[0], originals[2]]


@pytest.mark.parametrize("action", ["save", "discard"])
def test_repeated_review_returns_conflict_and_does_not_resolve_another_item(bridge, action):
    api, client = bridge
    add_candidates(client)
    item_id = pending(api)[0]["review_id"]
    assert review(api, action, item_id).status_code == 200
    before = client.session_store.get(client.session_id)
    knowledge_before = client.knowledge.all()
    assert review(api, action, item_id).status_code == 409
    assert client.session_store.get(client.session_id) == before
    assert client.knowledge.all() == knowledge_before


@pytest.mark.parametrize("count", [0, 3])
def test_missing_review_id_returns_conflict_for_empty_or_nonempty_session(bridge, count):
    api, client = bridge
    add_candidates(client, count)
    before = client.session_store.get(client.session_id)
    response = review(api, "discard", "missing-item")
    assert response.status_code == 409
    assert client.session_store.get(client.session_id) == before
    assert client.knowledge.all() == []


@pytest.mark.parametrize("item_id", [None, False, 7, [], {}, "", "   "])
def test_invalid_item_ids_never_fall_back_to_save_all(bridge, item_id):
    api, client = bridge
    add_candidates(client)
    before = client.session_store.get(client.session_id)
    response = review(api, "save", item_id)
    assert response.status_code == 400
    assert client.session_store.get(client.session_id) == before
    assert client.knowledge.all() == []


def test_failed_individual_save_keeps_every_candidate_for_retry(bridge):
    api, client = bridge
    originals = add_candidates(client)
    item_id = pending(api)[1]["review_id"]
    before = client.session_store.get(client.session_id)
    with patch.object(KnowledgeStore, "add_many", side_effect=OSError("unavailable")) as save:
        response = review(api, "save", item_id)
    assert response.status_code == 500
    save.assert_called_once_with([originals[1]])
    assert client.session_store.get(client.session_id) == before
    assert client.knowledge.all() == []
    assert review(api, "save", item_id).status_code == 200
    assert client.session_store.get(client.session_id)["candidates"] == [originals[0], originals[2]]


@pytest.mark.parametrize("action", ["save", "discard"])
def test_all_item_actions_still_resolve_remaining_candidates(bridge, action):
    api, client = bridge
    originals = add_candidates(client)
    assert review(api, "discard", pending(api)[1]["review_id"]).status_code == 200
    response = api.post("/api/session/learning", json={"action": action}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json["count"] == 2
    assert pending(api) == []
    expected = {originals[0]["query"], originals[2]["query"]} if action == "save" else set()
    assert {item["query"] for item in client.knowledge.all()} == expected


def test_individual_review_requires_pairing(bridge):
    api, client = bridge
    add_candidates(client)
    item_id = pending(api)[0]["review_id"]
    before = client.session_store.get(client.session_id)
    response = api.post("/api/session/learning", json={"action": "discard", "item_id": item_id})
    assert response.status_code == 401
    assert client.session_store.get(client.session_id) == before
