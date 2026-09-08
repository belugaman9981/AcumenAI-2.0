from dataclasses import dataclass
import re

@dataclass
class GateResult:
    kind: str
    confidence: float

GREETINGS = {
    "hi", "hello", "hey", "yo", "hiya", "sup", "what's up", "whats up",
    "good morning", "good afternoon", "good evening"
}
THANKS = {"thanks", "thank you", "thx", "ty"}
FAREWELLS = {"bye", "goodbye", "cya", "see you", "later"}

def classify_input(text):
    t = " ".join(text.lower().strip().split())
    bare = t.rstrip("!?.")

    if bare in GREETINGS:
        return GateResult("greeting", 0.99)
    if bare in THANKS:
        return GateResult("thanks", 0.99)
    if bare in FAREWELLS:
        return GateResult("farewell", 0.99)
    if t.startswith("/"):
        return GateResult("command", 1.0)
    if t.endswith("?") or re.match(r"^(what|who|where|when|why|how|is|are|do|does|did|can|could|would|should)\b", t):
        return GateResult("question", 0.95)
    if re.search(r"\b(is|are|was|were|has|have|contains|created by|invented by)\b", t):
        return GateResult("claim", 0.78)
    return GateResult("conversation", 0.60)
