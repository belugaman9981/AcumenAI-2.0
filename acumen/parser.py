from dataclasses import dataclass, field
import re
from .text import normalize, tokens

@dataclass
class ParsedInput:
    raw: str
    normalized: str
    tokens: list[str]
    is_question: bool
    wh_word: str | None = None
    entities: list[str] = field(default_factory=list)

def parse(text):
    n = normalize(text)
    low = n.lower()
    wh = None
    for candidate in ("what","who","where","when","why","how"):
        if low.startswith(candidate + " "):
            wh = candidate
            break

    entities = []
    for m in re.finditer(r"\b[A-Z][A-Za-z0-9'-]*(?:\s+[A-Z][A-Za-z0-9'-]*)*", n):
        value = m.group(0).strip()
        if value.lower() not in {"what","who","where","when","why","how"}:
            entities.append(value)

    return ParsedInput(
        raw=text,
        normalized=n,
        tokens=tokens(n),
        is_question=n.endswith("?") or low.startswith(
            ("what ","who ","where ","when ","why ","how ","is ","are ","does ","do ","did ","can ")
        ),
        wh_word=wh,
        entities=list(dict.fromkeys(entities)),
    )
