
from acumen.research import WebResearcher

CFG = {
    "max_search_results": 5,
    "max_pages_to_scrape": 3,
    "request_timeout": 10,
    "max_page_chars": 120000,
}

def test_why_ranking_prefers_explanation():
    r = WebResearcher(CFG)
    text = (
        "The sky is the region seen above Earth. "
        "The sky appears blue during the day because molecules in Earth's atmosphere "
        "scatter shorter blue wavelengths of sunlight more strongly than longer red wavelengths. "
        "Clouds can appear white or gray."
    )
    ranked = r.rank_sentences("why is the sky blue?", text)
    assert ranked
    assert "because" in ranked[0]["text"].lower()

def test_query_prefix_is_not_required_for_terms():
    r = WebResearcher(CFG)
    ranked = r.rank_sentences(
        "research why is the sky blue",
        "The sky appears blue because atmospheric molecules scatter blue light more strongly."
    )
    assert ranked
