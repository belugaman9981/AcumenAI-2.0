from dataclasses import dataclass
import re
from .relations import canonical_relation
from .text import normalize

@dataclass
class Triple:
    subject: str
    relation: str
    object: str
    confidence: float = 0.85

PATTERNS = [
    (re.compile(r"^(.+?)\s+is\s+the\s+capital\s+of\s+(.+?)[.!]?$", re.I), "capital_of"),
    (re.compile(r"^(.+?)\s+is\s+located\s+in\s+(.+?)[.!]?$", re.I), "located_in"),
    (re.compile(r"^(.+?)\s+is\s+in\s+(.+?)[.!]?$", re.I), "located_in"),
    (re.compile(r"^(.+?)\s+was\s+created\s+by\s+(.+?)[.!]?$", re.I), "created_by"),
    (re.compile(r"^(.+?)\s+was\s+invented\s+by\s+(.+?)[.!]?$", re.I), "created_by"),
    (re.compile(r"^all\s+(.+?)\s+are\s+(.+?)[.!]?$", re.I), "is_a"),
    (re.compile(r"^(.+?)\s+is\s+(?:a|an)\s+(.+?)[.!]?$", re.I), "is_a"),
    (re.compile(r"^(.+?)\s+are\s+(?:a|an)?\s*(.+?)[.!]?$", re.I), "is_a"),
    (re.compile(r"^(.+?)\s+has\s+(.+?)[.!]?$", re.I), "has"),
]

def clean_entity(value):
    return normalize(value).strip(" .?!").lower()

def extract_triples(text):
    n = normalize(text)
    for rx, relation in PATTERNS:
        m = rx.match(n)
        if m:
            s = clean_entity(m.group(1))
            o = clean_entity(m.group(2))
            if s and o and s != o:
                return [Triple(s, canonical_relation(relation), o)]
    return []
