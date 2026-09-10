ALIASES = {
    "capital": "capital_of",
    "capital_of": "capital_of",
    "located in": "located_in",
    "is in": "located_in",
    "created by": "created_by",
    "invented by": "created_by",
    "is a": "is_a",
    "type of": "is_a",
    "kind of": "is_a",
    "has": "has",
}

def canonical_relation(name):
    return ALIASES.get(name.strip().lower(), name.strip().lower().replace(" ", "_"))
