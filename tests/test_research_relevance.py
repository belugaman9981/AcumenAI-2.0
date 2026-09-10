from unittest.mock import patch

import pytest

from acumen.config import DEFAULTS
from acumen.research import WebResearcher


@pytest.fixture
def researcher():
    r = WebResearcher(DEFAULTS["research"])
    yield r
    r.close()


def test_screenshot_articles_cannot_answer_a_clock_question(researcher):
    query = "what is the time in shenzhen right now?"
    text = (
        "China Southern Airlines Flight 3456 was a scheduled domestic passenger flight to Shenzhen. "
        "Shenzhen is a prefecture-level city in Guangdong, China with a population of 17.5 million."
    )
    assert researcher.rank_sentences(query, text) == []
    with patch.object(researcher, "search", side_effect=AssertionError("static research must not run")):
        result = researcher.research(query)
    assert not result["ok"] and not result["learnable"]
    assert result["sources"] == []


def test_a_single_place_match_cannot_answer_a_population_question(researcher):
    assert not researcher.rank_sentences(
        "What is the population of Shenzhen?",
        "China Southern Airlines Flight 3456 was a scheduled domestic passenger flight to Shenzhen.",
    )
    assert researcher.rank_sentences(
        "What is the population of Shenzhen?",
        "Shenzhen had a population of 17.5 million in the 2020 census.",
    )


def test_why_requires_an_explanation_not_just_shared_words(researcher):
    assert not researcher.rank_sentences(
        "Why is the sky blue?", "The blue sky is a common subject in landscape paintings."
    )
    assert researcher.rank_sentences(
        "Why is the sky blue?",
        "The sky appears blue because air molecules scatter blue light more strongly.",
    )


def test_relevant_paraphrases_remain_usable(researcher):
    assert researcher.rank_sentences(
        "Who invented Python?", "Python was created by Guido van Rossum in the late 1980s."
    )
    assert researcher.rank_sentences(
        "How does photosynthesis work?",
        "Photosynthesis converts sunlight into chemical energy through reactions in plant cells.",
    )


def test_unrelated_snippets_do_not_turn_into_answers(researcher):
    source = {"title": "Sunday", "url": "https://example.org/sunday",
              "snippet": "Sunday is the first day of the week in many calendar traditions."}
    with patch.object(researcher, "search", return_value=[source]), \
         patch.object(researcher, "fetch_text", return_value=""):
        result = researcher.research("What is the sun?")
    assert not result["ok"] and not result["learnable"]
    assert result["sources"] == []
    assert "directly answers" in result["answer"]


def test_only_sentences_used_in_the_answer_supply_sources(researcher):
    good = {"title": "Sky", "url": "https://example.org/sky",
            "prefetched_text": "The sky appears blue because air molecules scatter blue light more strongly."}
    bad = {"title": "Painting", "url": "https://example.org/art",
           "prefetched_text": "The blue sky is a common subject in landscape paintings."}
    with patch.object(researcher, "search", return_value=[good, bad]):
        result = researcher.research("Why is the sky blue?")
    assert result["ok"]
    assert [source["url"] for source in result["sources"]] == [good["url"]]
    assert all(row["text"] in result["answer"] and row["url"] == good["url"] for row in result["evidence"])
