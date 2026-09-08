from dataclasses import dataclass
import re

@dataclass
class Intent:
    name: str
    confidence: float

def classify(parsed):
    t = parsed.normalized.lower()
    if re.match(r"^(what|which) is the capital of ", t):
        return Intent("relation_query", 0.99)
    if re.match(r"^where is ", t):
        return Intent("location_query", 0.95)
    if re.match(r"^(is|are) .+\?$", t):
        return Intent("boolean_query", 0.88)
    if parsed.is_question:
        return Intent("knowledge_query", 0.72)
    return Intent("statement", 0.75)
