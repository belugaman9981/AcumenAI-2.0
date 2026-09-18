"""End-to-end coverage for finding chat text and reviewing individual answers."""
from copy import deepcopy
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import pytest
from werkzeug.serving import make_server

from acumen.bridge import make_app
from acumen.config import DEFAULTS


def test_find_chat_and_review_individual_answers(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    config = deepcopy(DEFAULTS)
    config["web"]["pairing_token"] = "review-browser-token"
    app = make_app(tmp_path / "data", config)
    client = app.extensions["acumen_client"]
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with playwright.sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="chrome", headless=True)
            except playwright.Error as error:
                pytest.skip(f"Chrome unavailable: {error}")
            context = browser.new_context(viewport={"width": 1100, "height": 900})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script("localStorage.setItem('acumen_token', 'review-browser-token');")
            page.goto(f"http://localhost:{server.server_port}")
            playwright.expect(page.locator("#status")).to_contain_text("Connected and paired")
            for question, answer in [("calculate 6*7", "42"), ("calculate 5*5", "25")]:
                page.locator("#message").fill(question)
                page.locator("#message").press("Enter")
                playwright.expect(page.locator(".acumen .message-text").last).to_contain_text(answer, timeout=15000)
                playwright.expect(page.locator("#sendBtn")).to_be_enabled()
            playwright.expect(page.locator("#learningCount")).to_have_text("(2)")
            page.locator("#message").fill("Keep my draft while I review")
            messages = page.locator(".message-text").all_text_contents()

            page.locator("#findChat").click()
            page.locator("#chatSearch").fill("CALCULATE")
            playwright.expect(page.locator("#chatSearchCount")).to_have_text("1 of 2")
            playwright.expect(page.locator(".chat-match")).to_have_count(2)
            page.locator("#nextMatch").click()
            playwright.expect(page.locator("#chatSearchCount")).to_have_text("2 of 2")
            page.locator("#chatSearch").press("Enter")
            playwright.expect(page.locator("#chatSearchCount")).to_have_text("1 of 2")
            page.locator("#chatSearch").press("Shift+Enter")
            playwright.expect(page.locator("#chatSearchCount")).to_have_text("2 of 2")
            page.locator("#previousMatch").click()
            playwright.expect(page.locator("#chatSearchCount")).to_have_text("1 of 2")
            page.locator("#chatSearch").fill("6*7")
            playwright.expect(page.locator(".chat-match")).to_have_text(["6*7"])
            page.locator("#chatSearch").fill("[<unmatched>")
            playwright.expect(page.locator("#chatSearchCount")).to_have_text("No matches")
            playwright.expect(page.locator("#nextMatch")).to_be_disabled()
            playwright.expect(page.locator(".message-text")).to_have_text(messages)
            page.locator("#chatSearch").fill("calculate")
            with page.expect_download() as download:
                page.locator("#exportChat").click()
            exported = Path(download.value.path()).read_text(encoding="utf-8")
            assert "calculate 6*7" in exported and "<mark" not in exported
            page.locator("#chatSearch").press("Escape")
            playwright.expect(page.locator("#chatSearchPanel")).not_to_be_visible()
            playwright.expect(page.locator(".chat-match")).to_have_count(0)
            playwright.expect(page.locator("#message")).to_have_value("Keep my draft while I review")

            page.locator("#learningPanel summary").click()
            first = page.locator("#learning .knowledge-item").filter(has_text="calculate 6*7")
            playwright.expect(first).to_contain_text("Supported by a local symbolic calculation.")
            first.get_by_role("button", name="Save answer", exact=True).click()
            playwright.expect(page.locator("#learningCount")).to_have_text("(1)")
            assert [item["answer"] for item in client.knowledge.all()] == ["42"]
            remaining = page.locator("#learning .knowledge-item")
            playwright.expect(remaining).to_contain_text("calculate 5*5")
            page.once("dialog", lambda dialog: dialog.dismiss())
            remaining.get_by_role("button", name="Discard answer", exact=True).click()
            playwright.expect(page.locator("#learningCount")).to_have_text("(1)")
            page.once("dialog", lambda dialog: dialog.accept())
            remaining.get_by_role("button", name="Discard answer", exact=True).click()
            playwright.expect(page.locator("#learningCount")).to_have_text("(0)")
            assert [item["answer"] for item in client.knowledge.all()] == ["42"]
            playwright.expect(page.locator("#message")).to_have_value("Keep my draft while I review")

            # Research answers go through the real chat endpoint and review UI.
            question = "Why is the sky blue?"
            answer = "The sky is blue because air scatters blue light."
            alternate = "Air scatters short wavelengths strongly, making the sky appear blue."

            def result(text):
                return {"ok": True, "answer": text, "confidence": .7,
                        "sources": [{"url": "https://example.org/sky", "title": "Sky"}],
                        "evidence": [{"url": "https://example.org/sky", "text": text, "kind": "page"}]}

            with patch.object(client.local_processor.researcher, "research", return_value=result(answer)) as research:
                page.locator("#message").fill(question)
                page.locator("#message").press("Enter")
                playwright.expect(page.locator(".acumen .message-text").last).to_contain_text(answer)
                playwright.expect(page.locator("#learningCount")).to_have_text("(1)")
                candidate = page.locator("#learning .knowledge-item")
                playwright.expect(candidate).to_contain_text("New answer")
                playwright.expect(candidate).to_contain_text("1 supported passage from 1 source page.")
                candidate.get_by_role("button", name="Save answer", exact=True).click()
                playwright.expect(page.locator("#learningCount")).to_have_text("(0)")
                page.locator("#message").fill(question)
                page.locator("#message").press("Enter")
                playwright.expect(page.locator("#sendBtn")).to_be_enabled()
                playwright.expect(page.locator(".acumen .message-text").last).to_contain_text(answer)
                assert research.call_count == 1

            with patch.object(client.local_processor.researcher, "research", return_value=result(alternate)):
                client.local_processor.process("research", {"query": question}, client.session_id)
            page.reload()
            playwright.expect(page.locator("#status")).to_contain_text("Connected and paired")
            playwright.expect(page.locator("#learningCount")).to_have_text("(1)")
            if not page.locator("#learningPanel").evaluate("element => element.open"):
                page.locator("#learningPanel > summary").click()
            candidate = page.locator("#learning .knowledge-item")
            playwright.expect(candidate).to_contain_text("Different answer to review")
            candidate.get_by_text("Compare other answers", exact=True).click()
            playwright.expect(candidate).to_contain_text(answer)
            playwright.expect(candidate).to_contain_text(alternate)
            page.set_viewport_size({"width": 320, "height": 640})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(tmp_path / "learning-review-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1100, "height": 900})
            page.screenshot(path=str(tmp_path / "learning-review-desktop.png"), full_page=True)
            candidate.get_by_role("button", name="Save answer", exact=True).click()
            playwright.expect(page.locator("#learningCount")).to_have_text("(0)")
            assert {item["answer"] for item in client.knowledge.all()} == {"42", answer, alternate}

            page.set_viewport_size({"width": 320, "height": 640})
            page.locator("#findChat").click()
            page.locator("#chatSearch").fill("calculate")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator("#clearChat").click()
            playwright.expect(page.locator("#chatSearchPanel")).not_to_be_visible()
            playwright.expect(page.locator("#findChat")).to_be_disabled()
            assert not errors
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        client.local_processor.close()
