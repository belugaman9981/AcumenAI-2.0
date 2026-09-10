from unittest.mock import Mock, patch

from acumen.research import WebResearcher


CFG = {
    "max_search_results": 5, "max_pages_to_scrape": 3,
    "request_timeout": 10, "max_page_chars": 120000,
}
SOURCE = {"title": "Sky", "url": "https://example.org/sky", "snippet": "The sky appears blue."}


def researcher(**config):
    r = WebResearcher(dict(CFG, **config))
    r._ddg_instant_answer = Mock(return_value=[dict(SOURCE)])
    r._wikipedia_search = Mock(return_value=[])
    r._ddg_html_search = Mock(return_value=[])
    return r


def test_search_cache_normalization_copy_and_expiry():
    r = researcher(cache_ttl_seconds=10)
    try:
        with patch("acumen.research.time.monotonic", return_value=100):
            first = r.search("research why is the sky blue")
            first[0]["title"] = "Caller changed it"
            assert r.search("WHY IS THE SKY BLUE")[0]["title"] == "Sky"
            assert r._ddg_instant_answer.call_count == 1
        with patch("acumen.research.time.monotonic", return_value=111):
            r.search("why is the sky blue")
        assert r._ddg_instant_answer.call_count == 2
    finally:
        r.close()


def test_failed_search_is_not_cached_and_one_worker_completes():
    r = researcher(max_workers=1)
    try:
        r._ddg_instant_answer.side_effect = [RuntimeError("provider down"), [SOURCE]]
        assert r.search("sky") == []
        assert r.search("sky")[0]["title"] == "Sky"
    finally:
        r.close()


def test_cache_is_bounded_and_can_be_disabled():
    r = researcher(cache_max_entries=1)
    try:
        r.search("sky")
        r.search("ocean")
        r.search("sky")
        assert r._ddg_instant_answer.call_count == 3
    finally:
        r.close()
    r = researcher(cache_ttl_seconds=0)
    try:
        r.search("sky")
        r.search("sky")
        assert r._ddg_instant_answer.call_count == 2
    finally:
        r.close()


def test_volatile_search_bypasses_cached_pages():
    r = researcher()
    text = "The current sky color is blue because the air scatters blue light."
    response = Mock(headers={"content-type": "text/plain"}, encoding="utf-8")
    response.iter_content.side_effect = lambda **kwargs: iter([text.encode()])
    r.s = Mock()
    r.s.get.return_value = response
    try:
        r.fetch_text(SOURCE["url"])
        r.fetch_text(SOURCE["url"])
        assert r.s.get.call_count == 1
        assert r.research("current sky color")["ok"]
        assert r.research("current sky color")["ok"]
        assert r.s.get.call_count == 3
        assert r._ddg_instant_answer.call_count == 2
        assert response.close.call_count == 3
    finally:
        r.close()


def test_duplicate_urls_keep_the_more_useful_text():
    r = researcher()
    r._ddg_instant_answer.return_value = [dict(SOURCE, url=SOURCE["url"] + "#intro")]
    r._wikipedia_search.return_value = [dict(
        SOURCE, url=SOURCE["url"] + "?utm_source=search",
        prefetched_text="The sky appears blue because the air scatters blue light.",
    )]
    try:
        found = r.search("sky")
        assert len(found) == 1
        assert found[0]["url"] == SOURCE["url"]
        assert "because" in found[0]["prefetched_text"]
    finally:
        r.close()
