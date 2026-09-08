from dataclasses import dataclass
import re
from .text import canonical_entity

@dataclass
class Claim:
    subject: str
    relation: str
    object: str
    raw: str

PATTERNS = [
    (re.compile(r"^(.+?)\s+is\s+the\s+capital\s+of\s+(.+?)[.!]?$", re.I), "capital_of"),
    (re.compile(r"^(.+?)\s+is\s+located\s+in\s+(.+?)[.!]?$", re.I), "located_in"),
    (re.compile(r"^(.+?)\s+is\s+in\s+(.+?)[.!]?$", re.I), "located_in"),
    (re.compile(r"^(.+?)\s+was\s+created\s+by\s+(.+?)[.!]?$", re.I), "created_by"),
    (re.compile(r"^(.+?)\s+was\s+invented\s+by\s+(.+?)[.!]?$", re.I), "created_by"),
    (re.compile(r"^all\s+(.+?)\s+are\s+(.+?)[.!]?$", re.I), "is_a"),
    (re.compile(r"^(.+?)\s+is\s+(?:a|an)\s+(.+?)[.!]?$", re.I), "is_a"),
    (re.compile(r"^(.+?)\s+are\s+(?:a|an)?\s*(.+?)[.!]?$", re.I), "is_a"),
]

def extract_claim(text):
    for rx, relation in PATTERNS:
        m = rx.match(text.strip())
        if m:
            return Claim(
                canonical_entity(m.group(1)),
                relation,
                canonical_entity(m.group(2)),
                text.strip(),
            )
    return None
