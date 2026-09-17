"""Assess whether an answer has enough retained evidence to learn or reuse."""

from collections.abc import Mapping
import math
from urllib.parse import urlsplit


def _normalized_text(value):
    # Keep punctuation, negation and numbers: they can change a claim's meaning.
    return " ".join(value.split()).casefold() if isinstance(value, str) else ""


def _source_url(source):
    value = source.get("url") if isinstance(source, Mapping) else source
    return value.strip() if isinstance(value, str) else ""


def _web_url(value):
    if not value or any(character.isspace() or ord(character) < 32 for character in value):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.port != 0
        )
    except ValueError:
        return False


def _rows(value):
    return value if isinstance(value, (list, tuple)) else []


def _page_support(answer, sources, evidence):
    """Find complete cited passages present in the answer and their coverage."""
    cited_urls = {_source_url(source) for source in _rows(sources)}
    cited_urls = {url for url in cited_urls if _web_url(url)}
    retained = {}
    edges = {}
    for item in _rows(evidence):
        if not isinstance(item, Mapping) or item.get("kind") != "page":
            continue
        url = _source_url(item)
        passage = _normalized_text(item.get("text"))
        if url not in cited_urls or not passage:
            continue
        start = 0
        while (start := answer.find(passage, start)) >= 0:
            end = start + len(passage)
            # A retained passage must be complete, not a fragment of another word.
            if (start == 0 or answer[start - 1] == " ") and (
                end == len(answer) or answer[end] == " "
            ):
                retained.setdefault(passage, set()).add(url)
                edges.setdefault(start, set()).add(end + (end < len(answer)))
            start += 1

    # Follow whole passages separated by whitespace. This also permits different
    # evidence order and duplicate corroboration without dropping answer text.
    reachable = {0}
    for start in sorted(edges):
        if start in reachable:
            reachable.update(edges[start])
    supporting_urls = set().union(*retained.values()) if retained else set()
    return len(answer) in reachable, len(supporting_urls), len(retained)


def assess_learning(candidate):
    """Return an evidence assessment without changing the candidate.

    Web answers must consist entirely of retained, cited page passages. A URL
    alone, a search snippet or partial coverage cannot establish support. Local
    symbolic calculations are a separate supported case. Counts describe unique
    supporting web URLs and unique normalized page passages, respectively.
    """
    result = {
        "eligible": False,
        "reason": "No usable answer is available to learn.",
        "source_count": 0,
        "passage_count": 0,
        "support": "insufficient",
    }
    if not isinstance(candidate, Mapping):
        return result
    answer = _normalized_text(candidate.get("answer"))
    if not answer:
        return result

    covered, result["source_count"], result["passage_count"] = _page_support(
        answer, candidate.get("sources"), candidate.get("evidence"),
    )
    if candidate.get("learnable") is False:
        result["reason"] = "This answer is marked as unsuitable for learning."
        return result
    if candidate.get("ok") is False:
        result["reason"] = "An unsuccessful result cannot be learned."
        return result
    confidence = candidate.get("confidence")
    try:
        confident = not isinstance(confidence, bool) and math.isfinite(float(confidence)) and float(confidence) >= .6
    except (TypeError, ValueError, OverflowError):
        confident = False
    if not confident:
        result["reason"] = "Learning requires a finite confidence of at least 0.6."
        return result

    if _normalized_text(candidate.get("kind")) in {"math", "homework"} and any(
        _source_url(source) == "local://sympy" for source in _rows(candidate.get("sources"))
    ):
        result.update(eligible=True, support="calculation", reason="Supported by a local symbolic calculation.")
    elif covered:
        result.update(eligible=True, support="page", reason="Every part of the answer has retained page evidence.")
    elif result["passage_count"]:
        result["reason"] = "Retained page evidence supports only part of this answer."
    else:
        result["reason"] = "No retained page evidence from a cited web source supports this answer."
    return result
