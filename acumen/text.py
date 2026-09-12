import re
import unicodedata
from collections import Counter
import math

TOKEN_RE = re.compile(r"\d+(?:\.\d+)+|\w+(?:['-]\w+)*(?:\+\+|#)?", re.UNICODE)
STOPWORDS = {
    "a","an","the","is","are","was","were","be","been","being",
    "of","to","in","on","at","for","from","with","and","or","as",
    "what","who","where","when","why","how","does","do","did",
    "can","could","would","should","it","this","that"
}

ALIASES = {
    "usa": "united states",
    "u.s.a": "united states",
    "u.s.": "united states",
    "us": "united states",
    "uk": "united kingdom",
}

# Common contractions/abbreviations expanded before comparison so that
# "what's" and "what is" collapse to the same normalized form.
CONTRACTIONS = {
    "what's": "what is",
    "who's": "who is",
    "where's": "where is",
    "when's": "when is",
    "why's": "why is",
    "how's": "how is",
    "it's": "it is",
    "that's": "that is",
    "there's": "there is",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "can't": "cannot",
    "won't": "will not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "hasn't": "has not",
    "haven't": "have not",
    "i'm": "i am",
    "you're": "you are",
    "we're": "we are",
    "they're": "they are",
}

# Lightweight suffix stripping. Not a full stemmer, but enough to make
# "invented"/"invent", "cities"/"city" and "running"/"run" comparable.
_SUFFIXES = ("ing", "edly", "ies", "ied", "es", "ed", "ly", "s")


def normalize(text):
    return " ".join(text.strip().split())


def expand_contractions(text):
    """Expand common contractions so equivalent phrasings normalize together."""
    lowered = unicodedata.normalize("NFKC", text).casefold().replace("\u2019", "'")
    return re.sub(
        r"\b(?:" + "|".join(map(re.escape, CONTRACTIONS)) + r")\b",
        lambda match: CONTRACTIONS[match.group()], lowered,
    )


def stem(token):
    """Very small suffix stripper used for fuzzy token comparison."""
    if len(token) <= 4:
        return token
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def canonical_entity(text):
    value = unicodedata.normalize("NFKC", normalize(text)).strip(" .?!").lower()
    return ALIASES.get(value, value)


def tokens(text, remove_stopwords=False):
    out = [t.lower() for t in TOKEN_RE.findall(text)]
    if remove_stopwords:
        out = [t for t in out if t not in STOPWORDS]
    return out


def content_tokens(text):
    """Stopword-free, contraction-expanded, stemmed tokens for matching."""
    expanded = expand_contractions(text)
    return [stem(t) for t in tokens(expanded, remove_stopwords=True)]


def normalize_question(text):
    """Normalize surface wording without losing names, numbers or operators."""
    expanded = expand_contractions(text)
    return " ".join(expanded.split()).rstrip(" ?!.")


def cosine_text(a, b):
    av, bv = Counter(tokens(a, True)), Counter(tokens(b, True))
    if not av or not bv:
        return 0.0
    dot = sum(v * bv.get(k, 0) for k, v in av.items())
    na = math.sqrt(sum(v*v for v in av.values()))
    nb = math.sqrt(sum(v*v for v in bv.values()))
    return dot / (na * nb) if na and nb else 0.0


def jaccard(a_tokens, b_tokens):
    """Token-set Jaccard similarity, robust to word order and length."""
    a, b = set(a_tokens), set(b_tokens)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def similarity(a, b):
    """Blended similarity for question matching.

    Combines token-set Jaccard (order-insensitive, penalizes extra words)
    with a containment score (rewards one question fully covering the other)
    and a character-level ratio for near-miss spellings.
    """
    a_tokens, b_tokens = content_tokens(a), content_tokens(b)
    if not a_tokens or not b_tokens:
        return 0.0
    a_set, b_set = set(a_tokens), set(b_tokens)
    jac = len(a_set & b_set) / len(a_set | b_set)
    containment = len(a_set & b_set) / min(len(a_set), len(b_set))
    char = _char_ratio(normalize_question(a), normalize_question(b))
    return round(0.45 * jac + 0.40 * containment + 0.15 * char, 4)


def _char_ratio(a, b):
    """Dice coefficient over character bigrams (cheap fuzzy string match)."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) < 2 or len(b) < 2:
        return 0.0
    a_bigrams = {a[i:i + 2] for i in range(len(a) - 1)}
    b_bigrams = {b[i:i + 2] for i in range(len(b) - 1)}
    overlap = len(a_bigrams & b_bigrams)
    return 2 * overlap / (len(a_bigrams) + len(b_bigrams))
