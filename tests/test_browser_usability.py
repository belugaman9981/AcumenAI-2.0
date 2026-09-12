"""Optional real-browser test: install playwright and provide Chrome locally."""
from copy import deepcopy
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

import pytest
from werkzeug.serving import make_server

from acumen.bridge import make_app
from acumen.config import DEFAULTS


def test_browser_chat_and_learning(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    project = Path(__file__).resolve().parents[1]
    static = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(project / "docs")))
    origin = f"http://127.0.0.1:{static.server_port}"
    config = deepcopy(DEFAULTS)
    config["web"]["pairing_token"] = "browser-test-token"
    config["web"]["allowed_origins"] = [origin]
    app = make_app(tmp_path / "data", config)
    backend = make_server("127.0.0.1", 0, app, threaded=True)
    bridge_url = f"http://127.0.0.1:{backend.server_port}"
    threads = [Thread(target=server.serve_forever, daemon=True) for server in (static, backend)]
    for thread in threads:
        thread.start()
    client = app.extensions["acumen_client"]
    try:
        with playwright.sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="chrome", headless=True)
            except playwright.Error as error:
                pytest.skip(f"Chrome unavailable: {error}")
            context = browser.new_context(permissions=["clipboard-read", "clipboard-write"], viewport={"width": 1100, "height": 900})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(f"localStorage.setItem('acumen_bridge', {json.dumps(bridge_url)});")
            page.goto(origin)
            playwright.expect(page.locator("#status")).to_contain_text("Pairing token not accepted")
            page.locator("#settingsBtn").click()
            page.locator("#token").fill("browser-test-token")
            page.locator("#saveSettings").click()
            playwright.expect(page.locator("#status")).to_contain_text("Connected and paired")

            page.get_by_role("button", name="Solve an equation").click()
            playwright.expect(page.locator("#message")).to_have_value("Solve 2*x + 3 = 11")
            page.locator("#message").press("Shift+Enter")
            assert "\n" in page.locator("#message").input_value()
            page.locator("#message").press("Enter")
            playwright.expect(page.locator(".acumen .message-text").last).to_contain_text("x = 4")
            playwright.expect(page.locator("#learningCount")).to_have_text("(1)")
            page.locator(".acumen button").last.click()
            playwright.expect(page.locator(".acumen button").last).to_have_text("Copied")
            assert "x = 4" in page.evaluate("navigator.clipboard.readText()")

            page.locator("#showSources").uncheck()
            playwright.expect(page.locator("#sendBtn")).to_be_enabled()
            page.locator("#message").fill("calculate 3*7")
            page.locator("#message").press("Enter")
            playwright.expect(page.locator(".acumen .message-text").last).to_have_text("21")
            playwright.expect(page.locator("#learningCount")).to_have_text("(2)")
            page.locator("#learningPanel summary").click()
            page.locator("#saveLearning").click()
            playwright.expect(page.locator("#learningCount")).to_have_text("(0)")
            assert len(client.knowledge.all()) == 2
            page.get_by_text("Saved knowledge", exact=True).click()
            page.locator("#knowledgeSearch").fill("3*7")
            playwright.expect(page.locator("#knowledge .knowledge-item")).to_have_count(1)
            page.locator("#knowledgeSearch").fill("no-such-answer")
            playwright.expect(page.locator("#knowledge")).to_have_text("No matching saved knowledge.")

            with page.expect_download() as download:
                page.locator("#exportChat").click()
            assert "x = 4" in Path(download.value.path()).read_text(encoding="utf-8")

            original_execute = client._execute
            started, release = Event(), Event()

            def slow_execute(*args):
                started.set()
                release.wait(timeout=10)
                return original_execute(*args)

            with patch.object(client, "_execute", side_effect=slow_execute) as execute:
                try:
                    page.locator("#message").fill("calculate 20+2")
                    page.locator("#message").press("Enter")
                    assert started.wait(timeout=5)
                    playwright.expect(page.locator("#sendBtn")).to_be_disabled()
                    page.locator("#message").fill("My next draft")
                    page.locator("#message").press("Enter")
                    playwright.expect(page.locator("#message")).to_have_value("My next draft")
                    assert execute.call_count == 1
                finally:
                    release.set()
                playwright.expect(page.locator(".acumen .message-text").last).to_have_text("22")
            playwright.expect(page.locator("#message")).to_have_value("My next draft")
            playwright.expect(page.locator("#learningCount")).to_have_text("(1)")
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator("#discardLearning").click()
            playwright.expect(page.locator("#learningCount")).to_have_text("(0)")
            assert len(client.knowledge.all()) == 2

            # Simulate one network failure, then retry the same question successfully.
            page.route("**/api/chat", lambda route: route.abort(), times=1)
            page.locator("#message").fill("/help")
            page.locator("#message").press("Enter")
            playwright.expect(page.locator(".retry")).to_be_enabled()
            page.locator(".retry").click()
            playwright.expect(page.locator(".acumen .message-text").last).to_contain_text("starter questions")
            playwright.expect(page.locator("#sendBtn")).to_be_enabled()

            page.locator("#knowledgeSearch").fill("3*7")
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator(".delete-knowledge").click()
            playwright.expect(page.locator("#knowledge .knowledge-item")).to_have_count(0)
            assert len(client.knowledge.all()) == 1
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator("#clearChat").click()
            playwright.expect(page.locator(".msg")).to_have_count(0)
            assert len(client.knowledge.all()) == 1

            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(project / ".pytest_cache" / "acumen-mobile.png"), full_page=True)
            assert not errors
            context.close()
            browser.close()
    finally:
        for server in (static, backend):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)
        client.local_processor.close()
