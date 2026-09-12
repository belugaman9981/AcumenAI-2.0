from unittest.mock import patch

import pytest

from acumen.client import AcumenClient
from acumen.config import DEFAULTS
from acumen.knowledge import KnowledgeStore
from acumen.research import WebResearcher
from acumen.router import route, requires_fresh_data
from acumen.text import normalize_question


@pytest.fixture
def client(tmp_path):
    instance = AcumenClient("local", tmp_path, DEFAULTS)
    yield instance
    instance.local_processor.close()


def supported(answer="Ottawa is the capital of Canada.", **extra):
    return {
        "ok": True, "answer": answer, "confidence": .7,
        "sources": [{"title": "Canada", "url": "https://example.org/canada"}],
        **extra,
    }


def test_chat_reuses_pending_learning_then_saves_and_recalls_it(client):
    result = supported()
    with patch.object(client.local_processor.researcher, "research", return_value=result) as research:
        assert "Ottawa" in client.chat("What is the capital of Canada?")
        assert "Ottawa" in client.chat("What\u2019s the capital of Canada?")
        research.assert_called_once()
    candidates = client.session_store.get(client.session_id)["candidates"]
    assert len(candidates) == 1
    assert client.knowledge.all() == []
    with patch("builtins.input", return_value="s"):
        client.session_store.finalize_interactive(client.session_id, client.knowledge)
    with patch.object(client.local_processor.researcher, "research", side_effect=AssertionError("unexpected fetch")):
        assert "Ottawa" in client.chat("WHAT IS THE CAPITAL OF CANADA?")
    item = client.knowledge.all()[0]
    assert item["confidence"] == .7
    assert item["use_count"] == 1
    assert item["last_used_at"]


def test_explicit_search_bypasses_pending_answer(client):
    with patch.object(client.local_processor.researcher, "research", return_value=supported()) as research:
        client.chat("What is the capital of Canada?")
        client.chat("Search for what is the capital of Canada?")
        assert research.call_count == 2


def test_conflicting_saved_answers_are_researched_instead_of_guessed(client):
    question = "What is the capital of Canada?"
    client.knowledge.add({"query": question, "answer": "Ottawa", "confidence": .9})
    client.knowledge.add({"query": question, "answer": "Toronto", "confidence": .99})
    with patch.object(client.local_processor.researcher, "research", return_value=supported()) as research:
        assert "Ottawa" in client.chat(question)
        research.assert_called_once()
    assert all(item["use_count"] == 0 for item in client.knowledge.all())


def test_session_disagreement_also_prevents_saved_answer_reuse(client):
    question = "What is the capital of Canada?"
    client.knowledge.add({"query": question, "answer": "Toronto"})
    client.session_store.add_candidate(client.session_id, {"query": question, **supported()})
    with patch.object(client.local_processor.researcher, "research", return_value=supported()) as research:
        assert "Ottawa" in client.chat(question)
        research.assert_called_once()


@pytest.mark.parametrize("extra", [
    {"confidence": .2}, {"confidence": float("nan")}, {"confidence": "invalid"},
    {"sources": []}, {"learnable": False}, {"ok": False}, {"answer": "  "},
    {"sources": [{"title": "No evidence URL"}]},
    {"sources": [{"url": "https://"}]},
])
def test_weak_or_failed_results_do_not_become_learning(client, extra):
    with patch.object(client.local_processor.researcher, "research", return_value=supported(**extra)):
        client.chat("What is the capital of Canada?")
    assert client.session_store.get(client.session_id)["candidates"] == []


@pytest.mark.parametrize("question", ["Stock scores this week", "Hotel prices", "News this year"])
def test_volatile_questions_bypass_all_learning_and_caches(client, question):
    assert requires_fresh_data(question)
    client.knowledge.add({"query": question, "answer": "Stale"})
    with patch.object(client.local_processor.researcher, "research", return_value=supported("Fresh")) as research:
        client.chat(question)
        client.chat(question)
        assert research.call_count == 2
    assert client.session_store.get(client.session_id)["candidates"] == []
    assert client.knowledge.lookup(question) is None


@pytest.mark.parametrize("query, kind, force", [
    ("Photosynthesis", "research", False),
    ("Explain photosynthesis", "research", False),
    ("Could you please describe photosynthesis?", "research", False),
    ("Does water expand when it freezes?", "research", False),
    ("Please search for photosynthesis", "research", True),
    ("Ottawa has parks", "verify", True),
    ("Okay", "conversation", False),
    ("Never mind", "conversation", False),
])
def test_question_and_topic_routing(query, kind, force):
    result = route(query)
    assert (result.kind, result.force_web) == (kind, force)


@pytest.mark.parametrize("stored, different", [
    ("What is C++?", "What is C?"),
    ("What is Python 3.12?", "What is Python 3.13?"),
    ("Can water freeze?", "Can't water freeze?"),
    ("Who defeated Alice?", "Who did Alice defeat?"),
    ("What is \u6771\u4eac?", "What is \u5317\u4eac?"),
])
def test_matching_preserves_meaningful_query_differences(tmp_path, stored, different):
    store = KnowledgeStore(tmp_path)
    store.add({"query": stored, "answer": "Stored answer"})
    assert store.lookup(different) is None
    assert store.lookup(stored)["answer"] == "Stored answer"


def test_contraction_normalization_is_word_bounded():
    assert normalize_question("What\u2019s Ottawa?") == normalize_question("What is Ottawa?")
    assert normalize_question("Showit's name") == "showit's name"


def test_normalized_duplicate_learning_merges_without_confidence_inflation(tmp_path):
    store = KnowledgeStore(tmp_path)
    first = store.add({"query": "What's Ottawa?", "answer": "A city", "confidence": .7})
    second = store.add({"query": "What is Ottawa?", "answer": "A city", "confidence": .7})
    assert first["id"] == second["id"]
    store.record_use(first["id"])
    store.record_use(first["id"])
    assert store.all()[0]["confidence"] == .7
    assert store.all()[0]["use_count"] == 2
    assert not store.record_use("missing")


@pytest.fixture
def researcher():
    instance = WebResearcher(DEFAULTS["research"])
    yield instance
    instance.close()


def test_explanation_prefix_and_contractions_do_not_pollute_ranking(researcher):
    sentence = "The sky appears blue because air molecules scatter blue light."
    assert researcher.rank_sentences("Could you please explain why the sky is blue?", sentence)
    assert researcher.rank_sentences("Why\u2019s the sky blue?", sentence)


def test_short_names_and_version_numbers_are_required_in_evidence(researcher):
    assert not researcher.rank_sentences(
        "What is Raspberry Pi 5?", "Raspberry Pi 4 is a compact single board computer.",
    )
    assert researcher.rank_sentences(
        "What is Raspberry Pi 5?", "Raspberry Pi 5 is a compact single board computer.",
    )
    assert not researcher.rank_sentences(
        "What is AI?", "Painting is an art form with a long history.",
    )
    assert researcher.rank_sentences(
        "What is AI?", "AI is the study of building systems that perform intelligent tasks.",
    )
    assert not researcher.rank_sentences(
        "What is Python 3.12?", "Python 12.3 is a fictional programming language release.",
    )
    assert not researcher.rank_sentences(
        "What is C++?", "C is a programming language originally developed in the 1970s.",
    )
    assert researcher.rank_sentences(
        "What is C++?", "C++ is a general purpose programming language developed by Bjarne Stroustrup.",
    )


def test_snippet_only_answer_is_available_but_not_learned(client):
    sentence = "Ottawa is the capital of Canada and lies on the Ottawa River."
    source = {"title": "Canada", "url": "https://example.org/canada", "snippet": sentence}
    researcher = client.local_processor.researcher
    with patch.object(researcher, "search", return_value=[source]), patch.object(researcher, "fetch_text", return_value=""):
        assert sentence in client.chat("What is the capital of Canada?")
    assert client.session_store.get(client.session_id)["candidates"] == []


def test_duplicate_passages_keep_corroborating_sources(researcher):
    sentence = "Ottawa is the capital of Canada and lies on the Ottawa River."
    sources = [
        {"title": "Canada", "url": url, "prefetched_text": sentence}
        for url in ["https://one.example/canada", "https://two.example/canada"]
    ]
    with patch.object(researcher, "search", return_value=sources):
        result = researcher.research("What is the capital of Canada?")
    assert result["answer"] == sentence
    assert result["learnable"]
    assert len(result["sources"]) == len(result["evidence"]) == 2
