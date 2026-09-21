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


@pytest.mark.parametrize("same_origin", [False, True], ids=["static-frontend", "localhost-website"])
def test_browser_chat_and_learning(tmp_path, same_origin):
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
    if same_origin:
        # Use localhost and an arbitrary port, with no stored bridge URL.
        origin = f"http://localhost:{backend.server_port}"
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
            chat_requests = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: chat_requests.append(request.url)
                    if request.method == "POST" and request.url.endswith("/api/chat") else None)
            if not same_origin:
                page.add_init_script(f"localStorage.setItem('acumen_bridge', {json.dumps(bridge_url)});")
            page.goto(origin)
            playwright.expect(page.locator("#status")).to_contain_text("Pairing token not accepted")
            page.locator("#settingsBtn").click()
            playwright.expect(page.locator("#bridgeUrl")).to_have_value(origin if same_origin else bridge_url)
            page.locator("#token").fill("wrong-token")
            page.locator("#saveSettings").click()
            playwright.expect(page.locator("#pairError")).to_contain_text("Pairing token not accepted")
            playwright.expect(page.locator("#settings")).to_be_visible()
            page.locator("#token").fill("browser-test-token")
            page.locator("#saveSettings").click()
            playwright.expect(page.locator("#status")).to_contain_text("Connected and paired")
            playwright.expect(page.locator("#settings")).not_to_be_visible()

            page.locator("#theme").select_option("dark")
            initial_height = page.locator("#message").bounding_box()["height"]
            page.locator("#message").fill("First line\nSecond line\nThird line\nFourth line")
            assert page.locator("#message").bounding_box()["height"] > initial_height
            page.locator("#message").fill("An unfinished question\nwith another line")
            page.reload()
            playwright.expect(page.locator("#status")).to_contain_text("Connected and paired")
            playwright.expect(page.locator("#message")).to_have_value("An unfinished question\nwith another line")
            playwright.expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.locator("#theme").select_option("light")
            playwright.expect(page.locator("html")).to_have_attribute("data-theme", "light")
            page.locator("#theme").select_option("system")
            playwright.expect(page.locator("html")).to_have_attribute("data-theme", "system")

            page.get_by_role("button", name="Solve an equation").click()
            playwright.expect(page.locator("#message")).to_have_value("Solve 2*x + 3 = 11")
            page.locator("#message").press("Shift+Enter")
            assert "\n" in page.locator("#message").input_value()
            page.locator("#message").press("Enter")
            # The first equation loads SymPy; allow cold-start time on slower PCs.
            playwright.expect(page.locator(".acumen .message-text").last).to_contain_text("x = 4", timeout=15000)
            playwright.expect(page.locator("#learningCount")).to_have_text("(1)")
            page.get_by_role("button", name="Copy", exact=True).last.click()
            playwright.expect(page.get_by_role("button", name="Copied", exact=True)).to_be_visible()
            assert "x = 4" in page.evaluate("navigator.clipboard.readText()")
            page.locator("#helpBtn").focus()
            page.keyboard.press("Control+K")
            playwright.expect(page.locator("#message")).to_be_focused()
            page.locator("#copyChat").click()
            playwright.expect(page.locator("#copyChat")).to_have_text("Copied")
            assert "You: Solve 2*x + 3 = 11" in page.evaluate("navigator.clipboard.readText()")
            assert page.evaluate("Object.keys(sessionStorage).filter(key => key.startsWith('acumen_draft:')).length") == 0
            page.locator("#message").press("ArrowUp")
            playwright.expect(page.locator("#message")).to_have_value("Solve 2*x + 3 = 11")

            page.locator("#showSources").uncheck()
            playwright.expect(page.locator("#sendBtn")).to_be_enabled()
            page.locator("#message").fill("calculate 3*7")
            page.locator("#message").press("Enter")
            playwright.expect(page.locator(".acumen .message-text").last).to_have_text("21")
            playwright.expect(page.locator("#learningCount")).to_have_text("(2)")
            playwright.expect(page.locator("#sendBtn")).to_be_enabled()
            page.locator("#message").fill("Keep my new draft")
            messages = page.locator(".message-text").all_text_contents()
            sent_count = len(chat_requests)
            page.reload()
            playwright.expect(page.locator("#status")).to_contain_text("Connected and paired")
            playwright.expect(page.locator(".message-text")).to_have_text(messages)
            playwright.expect(page.locator("#recentQuestions option")).to_have_count(3)
            playwright.expect(page.locator("#message")).to_have_value("Keep my new draft")
            assert len(chat_requests) == sent_count
            page.locator(".repeat").last.click()
            playwright.expect(page.locator("#sendBtn")).to_be_enabled()
            playwright.expect(page.locator(".acumen .message-text").last).to_have_text("21")
            playwright.expect(page.locator("#message")).to_have_value("Keep my new draft")
            playwright.expect(page.locator("#recentQuestions option")).to_have_count(3)
            page.locator("#recentQuestions").select_option("1")
            playwright.expect(page.locator("#message")).to_have_value("Solve 2*x + 3 = 11")
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
                    playwright.expect(page.locator("#activity")).to_be_visible()
                    page.locator("#message").fill("My next draft")
                    page.locator("#message").press("Enter")
                    playwright.expect(page.locator("#message")).to_have_value("My next draft")
                    page.locator("#chat").evaluate("element => { element.scrollTop = 0; }")
                    playwright.expect(page.locator("#latestMessage")).to_be_visible()
                    assert execute.call_count == 1
                finally:
                    release.set()
                playwright.expect(page.locator(".acumen .message-text").last).to_have_text("22")
            playwright.expect(page.locator("#activity")).not_to_be_visible()
            assert page.locator("#chat").evaluate("element => element.scrollTop") == 0
            page.emulate_media(reduced_motion="reduce")
            page.locator("#latestMessage").click()
            playwright.expect(page.locator("#latestMessage")).not_to_be_visible()
            assert page.locator(".msg").last.evaluate("element => getComputedStyle(element).animationName") == "none"
            playwright.expect(page.locator("#message")).to_have_value("My next draft")
            playwright.expect(page.locator("#learningCount")).to_have_text("(1)")

            # A failed refresh must not leave stale learning actions available.
            page.route("**/api/session", lambda route: route.abort(), times=1)
            page.locator("#reconnectBtn").click()
            playwright.expect(page.locator("#status")).to_contain_text("Could not reach Acumen")
            playwright.expect(page.locator("#saveLearning")).to_be_disabled()
            playwright.expect(page.locator("#discardLearning")).to_be_disabled()
            playwright.expect(page.locator("#learning .knowledge-item")).to_have_count(0)
            playwright.expect(page.locator("#learningCount")).not_to_have_text("(1)")
            playwright.expect(page.locator("#message")).to_have_value("My next draft")
            assert "33" in client.chat("calculate 30+3")
            page.locator("#reconnectBtn").click()
            playwright.expect(page.locator("#status")).to_contain_text("Connected and paired")
            playwright.expect(page.locator("#learningCount")).to_have_text("(2)")
            playwright.expect(page.locator("#saveLearning")).to_be_enabled()
            playwright.expect(page.locator("#message")).to_have_value("My next draft")
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator("#discardLearning").click()
            playwright.expect(page.locator("#learningCount")).to_have_text("(0)")
            assert len(client.knowledge.all()) == 2

            # Simulate one network failure, then retry the same question successfully.
            page.route("**/api/chat", lambda route: route.abort(), times=1)
            page.locator("#message").fill("/help")
            page.locator("#message").press("Enter")
            playwright.expect(page.locator(".retry")).to_be_enabled()
            messages = page.locator(".message-text").all_text_contents()
            sent_count = len(chat_requests)
            page.reload()
            playwright.expect(page.locator("#status")).to_contain_text("Connected and paired")
            playwright.expect(page.locator(".message-text")).to_have_text(messages)
            playwright.expect(page.locator(".retry")).to_be_enabled()
            assert len(chat_requests) == sent_count
            page.locator(".retry").click()
            playwright.expect(page.locator(".acumen .message-text").last).to_contain_text("starter questions")
            playwright.expect(page.locator("#sendBtn")).to_be_enabled()

            page.get_by_text("Saved knowledge", exact=True).click()
            page.locator("#knowledgeSearch").fill("3*7")
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator(".delete-knowledge").click()
            playwright.expect(page.locator("#knowledge .knowledge-item")).to_have_count(0)
            assert len(client.knowledge.all()) == 1
            page.locator("#theme").select_option("dark")
            page.screenshot(path=str(project / ".pytest_cache" / f"acumen-desktop-{same_origin}.png"), full_page=True)
            page.locator("#theme").select_option("light")
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator("#clearChat").click()
            playwright.expect(page.locator(".msg")).to_have_count(0)
            playwright.expect(page.locator("#recentQuestions")).to_be_disabled()
            playwright.expect(page.locator("#emptyChat")).to_be_visible()
            assert len(client.knowledge.all()) == 1
            sent_count = len(chat_requests)
            page.reload()
            playwright.expect(page.locator("#status")).to_contain_text("Connected and paired")
            playwright.expect(page.locator(".msg")).to_have_count(0)
            playwright.expect(page.locator("#recentQuestions")).to_be_disabled()
            playwright.expect(page.locator("#emptyChat")).to_be_visible()
            assert len(chat_requests) == sent_count

            # Recover the state left by a tab reload during an unfinished request.
            page.evaluate("""({url}) => sessionStorage.setItem(`acumen_chat:${url}`, JSON.stringify({
                version: 1,
                messages: [{role: "user", text: "calculate 5+5", retryQuestion: null, failed: false}],
                recentQuestions: ["calculate 5+5"],
                pendingQuestion: "calculate 5+5"
            }))""", {"url": origin if same_origin else bridge_url})
            page.reload()
            playwright.expect(page.locator("#status")).to_contain_text("Connected and paired")
            playwright.expect(page.locator(".acumen .message-text").last).to_contain_text("reloaded before the answer arrived")
            playwright.expect(page.locator(".retry")).to_be_enabled()
            playwright.expect(page.locator("#activity")).not_to_be_visible()
            assert len(chat_requests) == sent_count
            messages = page.locator(".message-text").all_text_contents()
            page.reload()
            playwright.expect(page.locator("#status")).to_contain_text("Connected and paired")
            playwright.expect(page.locator(".message-text")).to_have_text(messages)
            playwright.expect(page.locator(".retry")).to_be_enabled()
            assert len(chat_requests) == sent_count
            page.locator(".retry").click()
            playwright.expect(page.locator(".acumen .message-text").last).to_have_text("10")
            playwright.expect(page.locator("#sendBtn")).to_be_enabled()
            assert len(chat_requests) == sent_count + 1

            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator("#message").fill("A narrow screen draft\nwith a second line")
            assert page.locator("#sendBtn").bounding_box()["x"] >= 0
            page.screenshot(path=str(project / ".pytest_cache" / "acumen-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 320, "height": 640})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator("#settingsBtn").click()
            playwright.expect(page.locator("#token")).to_be_visible()
            page.get_by_role("button", name="Cancel", exact=True).click()
            playwright.expect(page.locator("#settings")).not_to_be_visible()
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


def test_browser_bridge_isolation_and_unavailable_storage():
    playwright = pytest.importorskip("playwright.sync_api")
    project = Path(__file__).resolve().parents[1]
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(project / "docs")))
    origin = f"http://127.0.0.1:{server.server_port}"
    other_bridge = f"{origin}/second"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with playwright.sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="chrome", headless=True)
            except playwright.Error as error:
                pytest.skip(f"Chrome unavailable: {error}")
            context = browser.new_context()
            page = context.new_page()
            errors, sent_questions, delayed = [], [], {}
            page.on("pageerror", lambda error: errors.append(str(error)))

            # Record completion after callers have processed each response, so
            # delayed-response assertions cannot pass before rendering finishes.
            page.add_init_script("""(() => {
                window.parsedApiResponses = [];
                const originalFetch = window.fetch;
                window.fetch = async (...args) => {
                    const response = await originalFetch(...args);
                    const originalJson = response.json.bind(response);
                    response.json = async () => {
                        const data = await originalJson();
                        setTimeout(() => window.parsedApiResponses.push(response.url), 0);
                        return data;
                    };
                    return response;
                };
            })();""")

            def fulfill(route, payload):
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

            def mock_api(route):
                request = route.request
                second = request.url.startswith(f"{other_bridge}/api/")
                if request.url.endswith("/api/session"):
                    if not second and "session" not in delayed:
                        delayed["session"] = route
                        return
                    candidates = [{"query": "Second bridge learning", "answer": "Second answer"}] if second else []
                    fulfill(route, {"candidates": candidates, "show_sources": True})
                elif request.url.endswith("/api/knowledge"):
                    if not second and "knowledge" not in delayed:
                        delayed["knowledge"] = route
                        return
                    fulfill(route, {"items": [{"id": "second", "query": "Second bridge knowledge", "answer": "Second saved answer"}] if second else []})
                elif request.url.endswith("/api/chat"):
                    sent_questions.append((request.url, request.post_data_json["message"]))
                    fulfill(route, {"reply": "Second bridge reply" if second else "Original bridge reply"})
                else:
                    route.fulfill(status=404)

            page.route("**/api/**", mock_api)
            page.goto(origin)
            playwright.expect(page.locator("#status")).to_contain_text("Checking connection")
            page.locator("#message").fill("Original bridge question")
            page.locator("#message").press("Enter")
            playwright.expect(page.locator(".acumen .message-text").last).to_have_text("Original bridge reply")
            playwright.expect(page.locator("#sendBtn")).to_be_enabled()
            page.locator("#message").fill("Original bridge draft")
            page.get_by_text("Saved knowledge", exact=True).click()
            playwright.expect(page.locator("#knowledge")).to_have_text("Loading…")

            page.locator("#settingsBtn").click()
            page.locator("#bridgeUrl").fill(other_bridge)
            page.locator("#token").fill("second-token")
            page.locator("#saveSettings").click()
            playwright.expect(page.locator("#settings")).not_to_be_visible()
            playwright.expect(page.locator("#status")).to_contain_text("Connected and paired")
            playwright.expect(page.locator("#learningCount")).to_have_text("(1)")
            playwright.expect(page.locator("#knowledge")).to_contain_text("Second bridge knowledge")
            playwright.expect(page.locator(".msg")).to_have_count(0)
            playwright.expect(page.locator("#message")).to_have_value("")

            # Complete both requests from the previous bridge after pairing.
            completed = page.evaluate("window.parsedApiResponses.length")
            fulfill(delayed["session"], {"candidates": [
                {"query": "Stale first learning", "answer": "Old answer"},
                {"query": "Another stale item", "answer": "Old answer"},
            ], "show_sources": False})
            page.wait_for_function("count => window.parsedApiResponses.length > count", arg=completed)
            completed = page.evaluate("window.parsedApiResponses.length")
            fulfill(delayed["knowledge"], {"items": [{"id": "stale", "query": "Stale first knowledge", "answer": "Old saved answer"}]})
            page.wait_for_function("count => window.parsedApiResponses.length > count", arg=completed)
            playwright.expect(page.locator("#learningCount")).to_have_text("(1)")
            playwright.expect(page.locator("#learning")).to_contain_text("Second bridge learning")
            playwright.expect(page.locator("#showSources")).to_be_checked()
            playwright.expect(page.locator("#knowledge")).to_contain_text("Second bridge knowledge")
            playwright.expect(page.locator("#knowledge")).not_to_contain_text("Stale first knowledge")
            playwright.expect(page.locator("#status")).to_contain_text("Connected and paired")

            # Returning to a bridge restores only that bridge's conversation.
            page.locator("#settingsBtn").click()
            page.locator("#bridgeUrl").fill(origin)
            page.locator("#token").fill("original-token")
            page.locator("#saveSettings").click()
            playwright.expect(page.locator("#settings")).not_to_be_visible()
            playwright.expect(page.locator("#reconnectBtn")).to_be_enabled()
            playwright.expect(page.locator(".message-text")).to_have_text(["Original bridge question", "Original bridge reply"])
            playwright.expect(page.locator("#message")).to_have_value("Original bridge draft")
            page.reload()
            playwright.expect(page.locator("#status")).to_contain_text("Connected and paired")

            # A slower connection check on the same bridge must not overwrite
            # the session state fetched after a newer completed chat request.
            delayed_check = {}

            def delay_check(route):
                delayed_check["route"] = route

            page.route(f"{origin}/api/session", delay_check, times=1)
            page.locator("#reconnectBtn").click()
            playwright.expect(page.locator("#status")).to_contain_text("Checking connection")
            page.locator("#message").fill("A question while reconnecting")
            page.locator("#message").press("Enter")
            playwright.expect(page.locator(".acumen .message-text").last).to_have_text("Original bridge reply")
            playwright.expect(page.locator("#sendBtn")).to_be_enabled()
            playwright.expect(page.locator("#learningCount")).to_have_text("(0)")
            completed = page.evaluate("window.parsedApiResponses.length")
            fulfill(delayed_check["route"], {"candidates": [{"query": "Outdated learning", "answer": "Old answer"}], "show_sources": False})
            page.wait_for_function("count => window.parsedApiResponses.length > count", arg=completed)
            playwright.expect(page.locator("#learningCount")).to_have_text("(0)")
            playwright.expect(page.locator("#showSources")).to_be_checked()

            # Shared localStorage can change in another tab; this tab must keep
            # its active bridge and its conversation until explicitly switched.
            page.evaluate("url => localStorage.setItem('acumen_bridge', url)", other_bridge)
            page.locator("#message").fill("Keep using the original bridge")
            page.locator("#message").press("Enter")
            playwright.expect(page.locator(".acumen .message-text").last).to_have_text("Original bridge reply")
            playwright.expect(page.locator("#sendBtn")).to_be_enabled()
            assert sent_questions[-1] == (f"{origin}/api/chat", "Keep using the original bridge")
            assert "Keep using the original bridge" in page.evaluate("url => sessionStorage.getItem(`acumen_chat:${url}`)", origin)
            assert page.evaluate("url => sessionStorage.getItem(`acumen_chat:${url}`)", other_bridge) is None

            # Same-bridge token correction must not replace an unsaved live
            # draft with the older stored value when storage writes fail.
            page.locator("#message").fill("An older saved draft")
            page.evaluate("""() => {
                Storage.prototype.setItem = function () { throw new DOMException('Storage unavailable', 'QuotaExceededError'); };
            }""")
            page.locator("#message").fill("Keep this live unsaved draft")
            page.locator("#settingsBtn").click()
            playwright.expect(page.locator("#bridgeUrl")).to_have_value(origin)
            page.locator("#token").fill("replacement-token")
            page.locator("#saveSettings").click()
            playwright.expect(page.locator("#settings")).not_to_be_visible()
            playwright.expect(page.locator("#reconnectBtn")).to_be_enabled()
            playwright.expect(page.locator("#message")).to_have_value("Keep this live unsaved draft")
            playwright.expect(page.locator("#composerHint")).to_contain_text("Browser storage unavailable")
            assert not errors
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
