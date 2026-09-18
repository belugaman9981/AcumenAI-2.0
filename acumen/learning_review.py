"""Explain learning changes without treating repeated answers as new evidence."""
from .knowledge import candidate_fingerprint, matching_answers, select_answer
from .learning import assess_learning


def _passages(candidate):
    answer = " ".join(candidate.get("answer", "").split()).casefold()
    supported = set()
    for item in candidate.get("evidence", []):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        passage = " ".join(item["text"].split()).casefold()
        if not passage or f" {passage} " not in f" {answer} ":
            continue
        # Use the same URL and evidence checks as the learning gate. Unused or
        # uncited passages must not make a repeat look like stronger evidence.
        assessment = assess_learning({"answer": item["text"], "kind": "research",
                                      "confidence": .6, "sources": candidate.get("sources", []),
                                      "evidence": [item]})
        if assessment["eligible"]:
            supported.add((item["url"].strip(), passage))
    return supported


def adds_evidence(candidate, saved):
    """A repeated fetch, higher score, or use count is not new support."""
    known = set().union(*(_passages(item) for item in saved)) if saved else set()
    return bool(_passages(candidate) - known)


def describe_learning(candidate, saved, pending=(), max_age_days=30):
    assessment = assess_learning(candidate)
    matches = matching_answers(saved, candidate.get("query", ""))
    key = candidate_fingerprint(candidate)
    same = [item for item in matches if candidate_fingerprint(item) == key]
    answer = " ".join(candidate.get("answer", "").split())
    answer_key = answer if candidate.get("kind") == "math" else answer.casefold()
    different = []
    for item in matches + matching_answers(pending, candidate.get("query", "")):
        other = " ".join(item.get("answer", "").split())
        other_key = other if candidate.get("kind") == "math" else other.casefold()
        if other_key != answer_key and other not in different:
            different.append(other)
    if different:
        status, label = "conflict", "Different answer to review"
        detail = "Another saved or pending answer differs. Compare the wording and sources before saving; Acumen will research again while versions disagree."
    elif same and adds_evidence(candidate, same):
        status, label = "evidence_update", "Adds supporting passages"
        detail = "This answer adds a page passage or source to the same saved answer. Saving merges the evidence."
    elif same and select_answer(same, candidate["query"], max_age_days=max_age_days) is None:
        status, label = "rechecked", "Rechecked saved answer"
        detail = "An older answer was researched again. Save it to retain the new research date."
    elif same:
        status, label = "already_saved", "Already saved"
        detail = "The same answer is already saved. Repetition alone does not increase confidence."
    else:
        status, label = "new", "New answer"
        detail = "Review the answer and its support before keeping it."
    return {**assessment, "status": status, "label": label, "detail": detail,
            "other_answers": different}
