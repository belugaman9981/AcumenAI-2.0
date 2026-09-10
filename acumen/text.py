import re
import unicodedata
from collections import Counter
import math

TOKEN_RE = re.compile(r"[A-Za-z0-9_'-]+", re.UNICODE)
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

def normalize(text):
    return " ".join(text.strip().split())

def canonical_entity(text):
    value = unicodedata.normalize("NFKC", normalize(text)).strip(" .?!").lower()
    return ALIASES.get(value, value)

def tokens(text, remove_stopwords=False):
    out = [t.lower() for t in TOKEN_RE.findall(text)]
    if remove_stopwords:
        out = [t for t in out if t not in STOPWORDS]
    return out

def cosine_text(a, b):
    av, bv = Counter(tokens(a, True)), Counter(tokens(b, True))
    if not av or not bv:
        return 0.0
    dot = sum(v * bv.get(k, 0) for k, v in av.items())
    na = math.sqrt(sum(v*v for v in av.values()))
    nb = math.sqrt(sum(v*v for v in bv.values()))
    return dot / (na * nb) if na and nb else 0.0
