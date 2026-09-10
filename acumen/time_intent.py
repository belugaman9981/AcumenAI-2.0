"""Recognize requests for a clock reading without treating all 'time' as a clock."""

import re


def _clock_query(text):
    query = " ".join(text.replace("’", "'").split()).strip(" ?!.")
    query = re.sub(
        r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?"
        r"(?:tell|show|give)\s+me\s+", "", query, flags=re.I,
    )
    query = re.sub(r"^(?:please\s+|look\s+up\s+|search\s+for\s+)", "", query, flags=re.I)
    query = re.sub(
        r"(?:\s*,?\s+(?:right\s+now|at\s+the\s+moment|currently|now|today|please))+$",
        "", query, flags=re.I,
    ).strip(" ,?!.")
    if query.lower() in {"what is time", "what's time", "what time"}:
        return False, None
    match = re.fullmatch(
        r"(?:what(?:'s|\s+is)?\s+)?(?:the\s+)?(?:(?:current|local)\s+)?"
        r"time(?:\s+is\s+it)?(?:\s+(?:in|at|for)\s+(.+))?",
        query, flags=re.I,
    )
    if match:
        return True, match.group(1)
    match = re.fullmatch(r"([\w, /'-]+?)\s+(?:(?:current|local)\s+)?time", query, flags=re.I)
    if match and not re.search(
        r"\b(what|who|where|why|how|when|explain|define|describe|about|best|travel|difference|saving)\b",
        match.group(1), re.I,
    ):
        return True, match.group(1)
    return False, None


def is_time_request(text):
    return _clock_query(text)[0]


def extract_time_location(text):
    return _clock_query(text)[1]
