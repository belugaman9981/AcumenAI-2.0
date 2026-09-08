import re
from .text import canonical_entity

def parse_relation_query(text):
    t = text.strip()
    patterns = [
        (re.compile(r"^(?:what|which) is the capital of (.+?)\??$", re.I), "capital_of"),
        (re.compile(r"^where is (.+?)\??$", re.I), "located_in"),
        (re.compile(r"^who created (.+?)\??$", re.I), "created_by"),
    ]
    for rx, relation in patterns:
        m = rx.match(t)
        if m:
            return canonical_entity(m.group(1)), relation
    return None

def parse_boolean_query(text):
    t = text.strip()
    m = re.match(r"^(?:is|are)\s+(.+?)\s+(?:a|an)?\s*(.+?)\??$", t, re.I)
    if not m:
        return None
    return canonical_entity(m.group(1)), "is_a", canonical_entity(m.group(2))
