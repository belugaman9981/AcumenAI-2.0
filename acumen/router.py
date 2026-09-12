import re
from dataclasses import dataclass
from .time_intent import is_time_request
from .text import expand_contractions

@dataclass
class Route:
    kind: str
    query: str
    force_web: bool = False

GREETINGS = {"hello", "hi", "hey", "yo", "hiya"}
THANKS = {"thanks", "thank you", "thx"}
FAREWELLS = {"bye", "goodbye", "later", "cya"}

# Verbs that signal the user wants information looked up rather than chatted about.
RESEARCH_VERBS = re.compile(
    r"\b(find|search|look up|lookup|research|browse|scrape)\b"
)
# Openers that introduce a topic the user wants explained.
TOPIC_OPENERS = re.compile(
    r"^(tell me about|explain|describe|give me|show me|what about|info on|information on)\b"
)

def requires_fresh_data(text):
    return is_time_request(text) or bool(re.search(
        r"\b(now|today|tonight|tomorrow|currently|current|latest|live|news|"
        r"weather|temperature|forecast|prices?|flights?|hotels?|stocks?|scores?|"
        r"this\s+(?:week|month|year))\b", text, re.I,
    ))

def route(text):
    raw = " ".join(text.strip().split())
    low = expand_contractions(raw).rstrip("!?. ")
    low = re.sub(r"^(?:please\s+|(?:can|could|would) you\s+(?:please\s+)?)(?=\w)", "", low)

    if low in GREETINGS:
        return Route("greeting", raw)
    if low in THANKS:
        return Route("thanks", raw)
    if low in FAREWELLS:
        return Route("farewell", raw)

    if raw.startswith("/"):
        return Route("command", raw)

    if is_time_request(raw):
        return Route("time", raw, force_web=True)

    if re.search(r"\b(homework|worksheet|assignment)\b", low):
        return Route("homework", raw, force_web=True)

    if re.search(r"\b(solve|calculate|evaluate)\b", low) and re.search(r"[0-9=+\-*/^x]", low):
        return Route("math", raw)

    if re.search(r"\bweather\b|\btemperature\b|\bforecast\b", low):
        return Route("weather", raw, force_web=True)

    if RESEARCH_VERBS.search(low):
        return Route("research", raw, force_web=True)

    if requires_fresh_data(raw) or re.search(r"\brestaurant\b", low):
        return Route("research", raw, force_web=True)

    if re.match(r"^(who|what|where|when|why|how|is|are|was|were|do|does|did|can|could|will|would|should|has|have)\b", low):
        return Route("research", raw, force_web=False)

    # A bare topic ("the Eiffel Tower", "quantum computing") is a lookup request,
    # not small talk. Treat short noun phrases without a verb as research.
    if TOPIC_OPENERS.search(low):
        return Route("research", raw, force_web=False)
    if _looks_like_topic(low):
        return Route("research", raw, force_web=False)

    # Factual-looking statement: verify it on the web instead of trusting it.
    if re.search(r"\b(is|are|was|were|has|have|means|causes)\b", low):
        return Route("verify", raw, force_web=True)

    return Route("conversation", raw)


def _looks_like_topic(low):
    """Heuristic: a short phrase with no verb is likely a lookup topic."""
    words = low.split()
    if not (1 <= len(words) <= 8) or not re.search(r"\w", low):
        return False
    if low in {"ok", "okay", "yes", "no", "sure", "fine", "nevermind", "never mind", "not now"}:
        return False
    if re.search(r"\b(is|are|was|were|be|do|does|did|can|will|would|should|"
                 r"has|have|means|causes|i|you|we|they|he|she|me|my|your)\b", low):
        return False
    return True
