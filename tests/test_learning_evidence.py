from copy import deepcopy

import pytest

from acumen.learning import assess_learning


ANSWER = "Ottawa is the capital of Canada."
URL = "https://example.org/canada"


def supported(**overrides):
    return {
        "query": "What is the capital of Canada?", "answer": ANSWER,
        "kind": "research", "confidence": .7,
        "sources": [{"url": URL}],
        "evidence": [{"text": ANSWER, "url": URL, "kind": "page"}],
        **overrides,
    }


def test_single_fetched_page_is_sufficient_without_mutating_candidate():
    candidate = supported()
    original = deepcopy(candidate)
    assert assess_learning(candidate) == {
        "eligible": True, "support": "page", "source_count": 1,
        "passage_count": 1,
        "reason": "Every part of the answer has retained page evidence.",
    }
    assert candidate == original


@pytest.mark.parametrize("overrides", [
    {"evidence": []},
    {"sources": []},
    {"evidence": [{"text": ANSWER, "url": URL, "kind": "snippet"}]},
    {"evidence": [{"text": ANSWER, "url": URL}]},
    {"evidence": [{"text": ANSWER, "url": "https://other.example", "kind": "page"}]},
    {"evidence": [{"text": "A completely different claim.", "url": URL, "kind": "page"}]},
    {"evidence": [ANSWER, None, 12]},
])
def test_sources_snippets_and_unattached_evidence_are_insufficient(overrides):
    result = assess_learning(supported(**overrides))
    assert not result["eligible"]
    assert result["support"] == "insufficient"
    assert result["source_count"] == result["passage_count"] == 0


@pytest.mark.parametrize("url", [
    "https://", "https:///canada", "ftp://example.org/canada", "file:///canada",
    "https://exam ple.org/canada", "https://example.org:bad/canada",
    "https://example.org:99999/canada", "https://[broken/canada",
    "https://user:password@example.org/canada", "https://example.org:0/canada",
])
def test_invalid_or_nonweb_sources_do_not_count(url):
    result = assess_learning(supported(
        sources=[{"url": url}],
        evidence=[{"text": ANSWER, "url": url, "kind": "page"}],
    ))
    assert not result["eligible"]
    assert result["source_count"] == result["passage_count"] == 0


@pytest.mark.parametrize("confidence", [None, False, True, "bad", .59, -1, float("nan"), float("inf"), float("-inf")])
def test_confidence_must_be_finite_and_high_enough(confidence):
    assert not assess_learning(supported(confidence=confidence))["eligible"]


@pytest.mark.parametrize("confidence", [.6, "0.6", .99])
def test_confidence_threshold_is_inclusive(confidence):
    assert assess_learning(supported(confidence=confidence))["eligible"]


@pytest.mark.parametrize("candidate", [None, [], "answer", {}, {"answer": "   "}, {"answer": 123}])
def test_missing_or_malformed_answer_has_stable_assessment(candidate):
    result = assess_learning(candidate)
    assert set(result) == {"eligible", "support", "reason", "source_count", "passage_count"}
    assert not result["eligible"]
    assert result["source_count"] == result["passage_count"] == 0
    assert result["reason"]


@pytest.mark.parametrize("overrides", [{"learnable": False}, {"ok": False}])
def test_explicitly_unlearnable_or_failed_answer_is_rejected(overrides):
    assert not assess_learning(supported(**overrides))["eligible"]


def test_whitespace_and_case_are_normalized_without_losing_passages():
    result = assess_learning(supported(answer="  OTTAWA\n is\t the capital of CANADA. "))
    assert result["eligible"]
    assert result["source_count"] == result["passage_count"] == 1


@pytest.mark.parametrize("answer,evidence", [
    ("Ottawa is not the capital of Canada.", ANSWER),
    ("There are 11 provinces.", "There are 10 provinces."),
    ("Python 3.12 is supported.", "Python 3.1.2 is supported."),
    ("C++ is supported.", "C is supported."),
    ("The answer is -2.", "The answer is 2."),
    ("It is safe.", "It is not true that It is safe."),
])
def test_meaningful_symbols_numbers_and_negation_are_preserved(answer, evidence):
    assert not assess_learning(supported(
        answer=answer,
        evidence=[{"text": evidence, "url": URL, "kind": "page"}],
    ))["eligible"]


def test_partial_support_never_qualifies_a_multi_sentence_answer():
    result = assess_learning(supported(answer=ANSWER + " It has ten million residents."))
    assert not result["eligible"]
    assert result["source_count"] == result["passage_count"] == 1
    assert "only part" in result["reason"]


def test_snippet_cannot_complete_missing_page_support():
    unsupported = "It has ten million residents."
    candidate = supported(answer=ANSWER + " " + unsupported)
    candidate["evidence"].append({"text": unsupported, "url": URL, "kind": "snippet"})
    result = assess_learning(candidate)
    assert not result["eligible"]
    assert result["passage_count"] == 1


def test_corroboration_counts_sources_without_duplicating_passages():
    candidate = supported()
    second_url = "https://other.example/canada"
    candidate["sources"].extend([{"url": second_url}, {"url": second_url}])
    candidate["evidence"].extend([
        {"text": "  OTTAWA is the capital of Canada. ", "url": second_url, "kind": "page"},
        {"text": ANSWER, "url": URL, "kind": "page"},
    ])
    result = assess_learning(candidate)
    assert result["eligible"]
    assert result["source_count"] == 2
    assert result["passage_count"] == 1


def test_multiple_passages_can_cover_answer_in_different_evidence_order():
    second = "It is in Ontario."
    candidate = supported(answer=ANSWER + " " + second)
    candidate["evidence"].insert(0, {"text": second, "url": URL, "kind": "page"})
    result = assess_learning(candidate)
    assert result["eligible"]
    assert result["source_count"] == 1
    assert result["passage_count"] == 2


def test_unrelated_citations_do_not_inflate_source_count():
    candidate = supported()
    candidate["sources"].append({"url": "https://other.example"})
    candidate["evidence"].append({"text": "An unrelated claim.", "url": "https://other.example", "kind": "page"})
    result = assess_learning(candidate)
    assert result["eligible"]
    assert result["source_count"] == result["passage_count"] == 1


def test_passage_fragments_cannot_be_stitched_into_new_words():
    result = assess_learning(supported(answer="Ottawa", evidence=[
        {"text": "Otta", "url": URL, "kind": "page"},
        {"text": "wa", "url": URL, "kind": "page"},
    ]))
    assert not result["eligible"]


@pytest.mark.parametrize("kind", ["math", "homework"])
def test_successful_local_calculation_is_a_distinct_support_type(kind):
    result = assess_learning({
        "query": "Calculate 2 + 2", "answer": "4", "confidence": .99,
        "kind": kind, "sources": [{"url": "local://sympy"}],
    })
    assert result["eligible"]
    assert result["support"] == "calculation"
    assert result["source_count"] == result["passage_count"] == 0


@pytest.mark.parametrize("overrides", [
    {"kind": "research"}, {"sources": [{"url": "local://other"}]},
    {"sources": []}, {"confidence": .4}, {"learnable": False},
])
def test_calculation_requires_matching_kind_source_and_quality(overrides):
    assert not assess_learning({
        "query": "Calculate 2 + 2", "answer": "4", "confidence": .99,
        "kind": "math", "sources": [{"url": "local://sympy"}], **overrides,
    })["eligible"]
