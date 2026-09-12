from copy import deepcopy
from unittest.mock import patch

import pytest

from acumen.bridge import make_app
from acumen.client import AcumenClient
from acumen.config import DEFAULTS


@pytest.fixture
def client(tmp_path):
    client = AcumenClient("local", tmp_path, DEFAULTS)
    yield client
    client.local_processor.close()


def test_help_history_repeat_and_sources(client):
    assert "starter questions" in client.chat("/help")
    assert "Solve" in client.chat("/examples")
    assert "No questions" in client.chat("/history")
    assert "Ask a question first" in client.chat("/again")
    assert "No sources" in client.chat("/sources")
    assert "Type a question" in client.chat(" ")
    client.chat("/hide-source")
    assert client.chat("solve 2*x + 3 = 11") == "x = 4"
    assert client.chat("/again") == "x = 4"
    assert "local://sympy" in client.chat("/sources")
    assert "You: solve 2*x + 3 = 11" in client.chat("/history")
    assert len(client.history) == 2


def test_history_is_bounded_and_commands_are_not_repeated(client):
    with patch.object(client, "_execute", return_value={"answer": "An answer"}):
        for i in range(35):
            client.chat(f"What is topic {i}?")
        client.chat("/help")
    assert len(client.history) == 30
    assert client.last_question == "What is topic 34?"


def test_save_and_discard_work_without_ending_session(client):
    session_id = client.session_id
    client.chat("calculate 6*7")
    assert "42" in client.chat("/learning")
    assert "Saved 1" in client.chat("/save")
    assert "Saved 0" in client.chat("/save")
    assert len(client.knowledge.all()) == 1
    client.chat("calculate 5*5")
    assert "Discarded 1" in client.chat("/discard")
    assert len(client.knowledge.all()) == 1
    assert client.session_id == session_id
    assert "No new learning" in client.chat("/learning")
    assert "42" in client.chat("/knowledge calculate 6*7")
    assert "No matching" in client.chat("/knowledge completelyunrelatedword")


def test_failed_save_retains_pending_learning(client):
    client.chat("calculate 6*7")
    with patch.object(client.local_processor.knowledge, "add_many", side_effect=OSError("disk unavailable")):
        with pytest.raises(OSError):
            client.chat("/save")
    assert len(client.session_store.get(client.session_id)["candidates"]) == 1


def test_pi_sends_learning_actions_to_worker(tmp_path):
    client = AcumenClient("pi", tmp_path, DEFAULTS)
    with patch.object(client.queue, "submit", return_value="job") as submit, \
         patch.object(client.queue, "wait", return_value={"answer": "Saved 2 learning item(s)."}), \
         patch.object(client.queue, "consume"):
        assert "Saved 2" in client.chat("/save")
    submit.assert_called_once_with("session_learning", {"query": "save"}, client.session_id)
    assert client.knowledge.all() == []


@pytest.fixture
def bridge(tmp_path):
    config = deepcopy(DEFAULTS)
    config["web"]["pairing_token"] = "test-token"
    app = make_app(tmp_path, config)
    app.testing = True
    yield app.test_client(), app.extensions["acumen_client"]
    app.extensions["acumen_client"].local_processor.close()


def test_browser_learning_api_preserves_saved_items_on_discard(bridge):
    api, client = bridge
    headers = {"X-Acumen-Token": "test-token"}
    assert api.get("/api/session").status_code == 401
    assert api.post("/api/session/learning", json={"action": "save"}).status_code == 401
    response = api.post("/api/chat", json={"message": "calculate 6*7"}, headers=headers)
    assert "42" in response.json["reply"]
    assert len(api.get("/api/session", headers=headers).json["candidates"]) == 1
    response = api.post("/api/session/learning", json={"action": "save"}, headers=headers)
    assert response.json["count"] == 1
    assert api.get("/api/session", headers=headers).json["candidates"] == []
    api.post("/api/chat", json={"message": "calculate 8*8"}, headers=headers)
    api.post("/api/session/learning", json={"action": "discard"}, headers=headers)
    items = api.get("/api/knowledge", headers=headers).json["items"]
    assert len(items) == 1 and items[0]["answer"] == "42"
    assert api.delete("/api/knowledge/missing", headers=headers).status_code == 404


@pytest.mark.parametrize("body", [None, [], {"action": []}, {"action": "delete"}, {}])
def test_invalid_learning_action_does_not_modify_session(bridge, body):
    api, client = bridge
    client.chat("calculate 4*4")
    response = api.post("/api/session/learning", json=body, headers={"X-Acumen-Token": "test-token"})
    assert response.status_code == 400
    assert len(client.session_store.get(client.session_id)["candidates"]) == 1


@pytest.mark.parametrize("body", [[], {"message": None}, {"message": {}}, {"message": " "}])
def test_invalid_chat_input_is_explained(bridge, body):
    api, _ = bridge
    response = api.post("/api/chat", json=body, headers={"X-Acumen-Token": "test-token"})
    assert response.status_code == 400
    assert response.json["error"]
