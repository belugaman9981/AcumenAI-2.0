from copy import deepcopy
import json
import logging
from unittest.mock import patch

import pytest

from acumen.bridge import make_app
from acumen.config import DEFAULTS


TOKEN_HEADERS = {"X-Acumen-Token": "resilience-test-token"}


@pytest.fixture
def bridge(tmp_path):
    config = deepcopy(DEFAULTS)
    config["web"]["pairing_token"] = TOKEN_HEADERS["X-Acumen-Token"]
    app = make_app(tmp_path, config)
    app.testing = True
    yield app, app.test_client(), app.extensions["acumen_client"]
    app.extensions["acumen_client"].local_processor.close()


def test_unexpected_failure_is_logged_without_exposing_details_and_server_recovers(bridge, caplog):
    _, api, client = bridge
    secret_detail = "private disk path and internal credentials"
    with patch.object(client, "chat", side_effect=OSError(secret_detail)), caplog.at_level(logging.ERROR):
        response = api.post("/api/chat", json={"message": "hello"}, headers=TOKEN_HEADERS)

    assert response.status_code == 500
    assert response.is_json
    assert "server terminal" in response.json["error"]
    assert secret_detail not in response.get_data(as_text=True)
    assert response.headers["Cache-Control"] == "no-store"
    assert any(record.exc_info and secret_detail in str(record.exc_info[1]) for record in caplog.records)

    recovered = api.post("/api/chat", json={"message": "/help"}, headers=TOKEN_HEADERS)
    assert recovered.status_code == 200
    assert "starter questions" in recovered.json["reply"]


def test_request_size_limit_accepts_boundary_and_rejects_larger_body_without_processing(bridge):
    app, api, client = bridge
    limit = app.config["MAX_CONTENT_LENGTH"]
    overhead = len(json.dumps({"message": ""}).encode("utf-8"))
    message = "x" * (limit - overhead)
    body = json.dumps({"message": message}).encode("utf-8")
    assert len(body) == limit

    with patch.object(client, "chat", return_value="accepted") as chat:
        accepted = api.post("/api/chat", data=body, content_type="application/json", headers=TOKEN_HEADERS)
        assert accepted.status_code == 200
        assert accepted.json == {"reply": "accepted"}
        chat.assert_called_once_with(message)
        chat.reset_mock()

        rejected = api.post("/api/chat", data=body + b" ", content_type="application/json", headers=TOKEN_HEADERS)
        assert rejected.status_code == 413
        assert rejected.is_json
        assert "Shorten your message" in rejected.json["error"]
        assert rejected.headers["Cache-Control"] == "no-store"
        chat.assert_not_called()


@pytest.mark.parametrize("body_size_offset, expected_status", [(-1, 200), (0, 200), (1, 413)])
def test_streamed_request_size_limit(bridge, body_size_offset, expected_status):
    app, api, client = bridge
    overhead = len(json.dumps({"message": ""}).encode("utf-8"))
    body = json.dumps({"message": "x" * (app.config["MAX_CONTENT_LENGTH"] + body_size_offset - overhead)})
    with patch.object(client, "chat", return_value="accepted") as chat:
        response = api.post(
            "/api/chat", data=body, content_type="application/json", headers=TOKEN_HEADERS,
            environ_overrides={"CONTENT_LENGTH": "", "wsgi.input_terminated": True},
        )
    assert response.status_code == expected_status
    assert response.is_json
    if expected_status == 413:
        chat.assert_not_called()
    else:
        chat.assert_called_once()


@pytest.mark.parametrize("path, method, expected_status", [
    ("/api/missing", "get", 404),
    ("/api/chat", "get", 405),
])
def test_http_errors_keep_status_and_method_headers(bridge, path, method, expected_status):
    _, api, _ = bridge
    response = getattr(api, method)(path, headers=TOKEN_HEADERS)
    assert response.status_code == expected_status
    assert response.is_json
    assert response.json["error"]
    assert response.headers["Cache-Control"] == "no-store"
    if expected_status == 405:
        assert "POST" in response.headers["Allow"]


@pytest.mark.parametrize("headers, expected_status", [(TOKEN_HEADERS, 200), ({}, 401)])
def test_private_api_responses_are_never_cached(bridge, headers, expected_status):
    _, api, _ = bridge
    response = api.get("/api/session", headers=headers)
    assert response.status_code == expected_status
    assert response.headers["Cache-Control"] == "no-store"
