"""Offline regressions for bounded research fetching and evidence selection."""

from threading import Barrier
from unittest.mock import Mock

import pytest
from requests.structures import CaseInsensitiveDict

from acumen.research import WebResearcher


CFG = {
    "max_search_results": 5,
    "max_pages_to_scrape": 3,
    "request_timeout": 10,
    "max_page_chars": 120000,
    "max_workers": 4,
    "cache_ttl_seconds": 300,
    "cache_max_entries": 128,
    "max_page_bytes": 524288,
}


@pytest.fixture
def researcher():
    instance = WebResearcher(dict(CFG))
    try:
        yield instance
    finally:
        instance.close()


def source(title, url, snippet=""):
    return {"title": title, "url": url, "snippet": snippet}


def test_search_providers_overlap_and_keep_provider_order(researcher, monkeypatch):
    rendezvous = Barrier(3, timeout=3)

    def provider(title, url):
        def run(*args, **kwargs):
            rendezvous.wait()
            return [source(title, url)]
        return run

    monkeypatch.setattr(researcher, "_ddg_instant_answer", provider("First", "https://first.example/a"))
    monkeypatch.setattr(researcher, "_wikipedia_search", provider("Second", "https://second.example/b"))
    monkeypatch.setattr(researcher, "_ddg_html_search", provider("Third", "https://third.example/c"))

    results = researcher.search("photosynthesis mechanism")

    assert [item["title"] for item in results] == ["First", "Second", "Third"]


def test_page_fetches_overlap_without_reordering_selected_sources(researcher, monkeypatch):
    rendezvous = Barrier(2, timeout=3)
    sources = [
        source("First source", "https://first.example/article"),
        source("Second source", "https://second.example/article"),
    ]
    monkeypatch.setattr(researcher, "search", lambda query: sources)

    def fetch(url):
        rendezvous.wait()
        if "first.example" in url:
            return "Photosynthesis converts sunlight into chemical energy in green plants."
        return "Photosynthesis uses chlorophyll to absorb sunlight in plant cells."

    monkeypatch.setattr(researcher, "fetch_text", fetch)
    result = researcher.research("photosynthesis")

    assert result["ok"]
    assert [item["url"] for item in result["sources"]] == [item["url"] for item in sources]
    assert {item["url"] for item in result["evidence"]} == {item["url"] for item in sources}
    for item in result["evidence"]:
        assert {"text", "url", "title", "score"} <= item.keys()
        assert item["text"] in result["answer"]


def test_rank_sentences_does_not_match_inside_another_word(researcher):
    unrelated = "Sunday is the first day of the week in many calendar traditions."
    relevant = "The sun supplies the light and heat that sustain life on Earth."

    assert not researcher.rank_sentences("sun", unrelated)
    assert researcher.rank_sentences("sun", relevant)


def test_research_does_not_promote_unrelated_search_snippet(researcher, monkeypatch):
    monkeypatch.setattr(
        researcher,
        "search",
        lambda query: [source("Calendar", "https://calendar.example/day", "Sunday is a day of rest in many cultures.")],
    )
    monkeypatch.setattr(researcher, "fetch_text", lambda url: "")

    result = researcher.research("sun")

    assert not result["ok"]
    assert not result.get("evidence")


def test_sources_only_include_selected_evidence(researcher, monkeypatch):
    sources = [
        source("Plant biology", "https://biology.example/plants"),
        source("Calendar", "https://calendar.example/day"),
    ]
    monkeypatch.setattr(researcher, "search", lambda query: sources)
    monkeypatch.setattr(
        researcher,
        "fetch_text",
        lambda url: (
            "Photosynthesis converts sunlight into chemical energy in green plants."
            if "biology.example" in url
            else "Sunday is the first day of the week in many calendar traditions."
        ),
    )

    result = researcher.research("photosynthesis")

    assert result["ok"]
    assert [item["url"] for item in result["sources"]] == [sources[0]["url"]]
    assert all(item["url"] == sources[0]["url"] for item in result["evidence"])


def test_wikipedia_fetches_extracts_in_one_batch_and_restores_search_order(researcher):
    response_search = Mock()
    response_search.json.return_value = {
        "query": {"search": [
            {"title": "Alpha", "pageid": 1, "snippet": "First result"},
            {"title": "Beta", "pageid": 2, "snippet": "Second result"},
        ]}
    }
    response_extracts = Mock()
    response_extracts.json.return_value = {
        "query": {"pages": {
            "2": {"pageid": 2, "title": "Beta", "extract": "Beta is the second letter of the Greek alphabet."},
            "1": {"pageid": 1, "title": "Alpha", "extract": "Alpha is the first letter of the Greek alphabet."},
        }}
    }
    session = Mock()
    session.get.side_effect = [response_search, response_extracts]
    researcher.s = session

    results = researcher._wikipedia_search("Greek alphabet", limit=2)

    assert session.get.call_count == 2
    extract_params = session.get.call_args_list[1].kwargs["params"]
    assert extract_params["titles"] == "Alpha|Beta"
    assert extract_params["exlimit"] == "max"
    assert [item["title"] for item in results] == ["Alpha", "Beta"]
    assert results[0]["prefetched_text"].startswith("Alpha is")
    assert results[1]["prefetched_text"].startswith("Beta is")


class StreamingResponse:
    def __init__(self, chunks, content_type="text/html; charset=utf-8"):
        self.chunks = chunks
        self.headers = CaseInsensitiveDict({"Content-Type": content_type})
        self.encoding = "utf-8"
        self.status_code = 200
        self.closed = False
        self.chunks_read = 0

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=8192, **kwargs):
        for chunk in self.chunks:
            self.chunks_read += 1
            yield chunk

    def close(self):
        self.closed = True

    @property
    def text(self):
        raise AssertionError("Fetching should consume the bounded stream, not response.text")


def test_fetch_extracts_article_and_closes_response(researcher):
    response = StreamingResponse([
        b"<html><body><nav>Navigation noise</nav><article><h1>Photosynthesis</h1>"
        b"<p>Plants convert sunlight into chemical energy.</p>"
        b"<p>Chlorophyll absorbs the light used in this process.</p>"
        b"<script>trackingNoise()</script></article><footer>Footer noise</footer></body></html>"
    ])
    session = Mock()
    session.get.return_value = response
    researcher.s = session

    text = researcher.fetch_text("https://biology.example/plants")

    assert "Plants convert sunlight into chemical energy." in text
    assert "Chlorophyll absorbs" in text
    assert "Navigation noise" not in text
    assert "Footer noise" not in text
    assert "trackingNoise" not in text
    assert response.closed
    assert session.get.call_args.kwargs["stream"] is True


def test_fetch_caps_download_before_later_chunks():
    instance = WebResearcher({**CFG, "max_page_bytes": 1024})
    response = StreamingResponse([
        b"A" * 1024,
        b"SHOULD_NOT_APPEAR" * 64,
        b"LATER_CHUNK" * 64,
    ], content_type="text/plain")
    session = Mock()
    session.get.return_value = response
    instance.s = session
    try:
        text = instance.fetch_text("https://biology.example/large.txt")
        assert "SHOULD_NOT_APPEAR" not in text
        assert "LATER_CHUNK" not in text
        assert len(text) == 1024
        assert response.chunks_read == 1
        assert response.closed
    finally:
        instance.close()


def test_fetch_closes_rejected_content_type(researcher):
    response = StreamingResponse([b"binary"], content_type="application/octet-stream")
    session = Mock()
    session.get.return_value = response
    researcher.s = session

    assert not researcher.fetch_text("https://biology.example/file.bin")
    assert response.closed
    assert response.chunks_read == 0


def test_duplicate_tracking_urls_share_one_result_and_keep_richer_content(researcher, monkeypatch):
    monkeypatch.setattr(
        researcher,
        "_ddg_instant_answer",
        lambda query: [source("Plant biology", "https://biology.example/plants?utm_source=news#summary", "Brief summary")],
    )
    monkeypatch.setattr(
        researcher,
        "_wikipedia_search",
        lambda *args, **kwargs: [{
            **source("Plant biology", "https://biology.example/plants", "A substantially more detailed summary of photosynthesis."),
            "prefetched_text": "Photosynthesis converts sunlight into chemical energy in green plants.",
        }],
    )
    monkeypatch.setattr(researcher, "_ddg_html_search", lambda query: [])

    results = researcher.search("photosynthesis")

    assert len(results) == 1
    assert results[0]["prefetched_text"].startswith("Photosynthesis converts")
    assert "substantially more detailed" in results[0]["snippet"]


def test_search_cache_normalizes_queries_and_returns_independent_results(researcher, monkeypatch):
    provider = Mock(return_value=[source("Plant biology", "https://biology.example/plants", "Original snippet")])
    monkeypatch.setattr(researcher, "_ddg_instant_answer", provider)
    monkeypatch.setattr(researcher, "_wikipedia_search", lambda *args, **kwargs: [])
    monkeypatch.setattr(researcher, "_ddg_html_search", lambda query: [])

    first = researcher.search("  Photosynthesis   mechanism  ")
    first[0]["snippet"] = "Caller mutation"
    second = researcher.search("photosynthesis mechanism")

    assert provider.call_count == 1
    assert second[0]["snippet"] == "Original snippet"
