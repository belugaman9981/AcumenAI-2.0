"""The website and protected API must work from a single localhost server."""
from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from unittest.mock import patch

import pytest

from acumen.bridge import make_app, main
from acumen.config import DEFAULTS


@pytest.fixture
def website(tmp_path):
    app = make_app(tmp_path / "data", deepcopy(DEFAULTS))
    app.testing = True
    yield app, app.test_client()
    app.extensions["acumen_client"].local_processor.close()


@pytest.mark.parametrize("path,content_type", [
    ("/", "text/html"), ("/index.html", "text/html"),
    ("/app.js", "javascript"), ("/style.css", "text/css"),
])
def test_website_assets_load_without_pairing(website, path, content_type):
    app, browser = website
    response = browser.get(path)
    assert response.status_code == 200
    assert content_type in response.content_type
    assert app.config["ACUMEN_PAIRING_TOKEN"].encode() not in response.data
    assert browser.head(path).status_code == 200


def test_default_token_is_private_and_api_still_requires_pairing(website):
    app, browser = website
    token = app.config["ACUMEN_PAIRING_TOKEN"]
    assert token != "change-me" and len(token) >= 32
    for path in ("/api/session", "/api/knowledge"):
        assert browser.get(path).status_code == 401
        assert browser.get(path, headers={"X-Acumen-Token": "change-me"}).status_code == 401
        assert browser.get(path, headers={"X-Acumen-Token": token}).status_code == 200
    response = browser.post("/api/chat", json={"message": "calculate 6*7"},
                            headers={"X-Acumen-Token": token})
    assert "42" in response.json["reply"]


@pytest.mark.parametrize("path", ["/config.yaml", "/data/knowledge.json", "/README.md", "/../config.yaml", "/static/config.yaml"])
def test_website_never_serves_project_or_private_files(website, path):
    app, browser = website
    response = browser.get(path, headers={"X-Acumen-Token": app.config["ACUMEN_PAIRING_TOKEN"]})
    assert response.status_code == 404


def test_launcher_uses_configured_storage(tmp_path, capsys):
    config = deepcopy(DEFAULTS)
    config["storage"]["root"] = str(tmp_path / "custom-data")
    config["web"]["pairing_token"] = "configured-token"
    with patch("sys.argv", ["bridge.py", "--port", "8888"]), \
         patch("acumen.bridge.load_config", return_value=config), \
         patch("flask.Flask.run") as run:
        main()
    run.assert_called_once_with(host="127.0.0.1", port=8888, debug=False)
    assert (tmp_path / "custom-data").is_dir()
    output = capsys.readouterr().out
    assert "http://127.0.0.1:8888" in output
    assert "Pairing token: configured-token" in output


@pytest.mark.parametrize("port", ["0", "-1", "65536"])
def test_launcher_rejects_invalid_port_before_initializing_storage(port):
    with patch("sys.argv", ["bridge.py", "--port", port]), \
         patch("acumen.bridge.make_app") as make, pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    make.assert_not_called()


def test_real_launcher_serves_website_and_chat_from_another_directory(tmp_path):
    project = Path(__file__).resolve().parents[1]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    log = tmp_path / "server.log"
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            [sys.executable, "-B", str(project / "bridge.py"), "--port", str(port)],
            cwd=tmp_path, stdout=output, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 20
            while True:
                assert process.poll() is None, log.read_text(encoding="utf-8")
                try:
                    with urlopen(url + "/health", timeout=1) as response:
                        assert json.load(response)["ok"]
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        pytest.fail(log.read_text(encoding="utf-8"))
                    time.sleep(0.1)
            token = next(line.split(": ", 1)[1] for line in log.read_text(encoding="utf-8").splitlines()
                         if line.startswith("Pairing token: "))
            with urlopen(url, timeout=5) as response:
                assert b'<title>AcumenAI</title>' in response.read()
            request = Request(url + "/api/chat", data=json.dumps({"message": "calculate 6*7"}).encode(),
                              headers={"Content-Type": "application/json", "X-Acumen-Token": token})
            with urlopen(request, timeout=10) as response:
                assert "42" in json.load(response)["reply"]
            assert (tmp_path / "data").is_dir()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
