import re
from dataclasses import dataclass
from .time_intent import is_time_request

@dataclass
class Route:
    kind: str
    query: str
    force_web: bool = False

GREETINGS = {"hello", "hi", "hey", "yo", "hiya"}
THANKS = {"thanks", "thank you", "thx"}
FAREWELLS = {"bye", "goodbye", "later", "cya"}

def requires_fresh_data(text):
    return is_time_request(text) or bool(re.search(
        r"\b(now|today|tonight|tomorrow|currently|current|latest|live|news|"
        r"weather|temperature|forecast|prices?|flights?|hotels?)\b", text, re.I,
    ))

def route(text):
    raw = " ".join(text.strip().split())
    low = raw.lower().rstrip("!?. ")

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

    if re.search(r"\b(find|search|look up|lookup|research|browse|scrape)\b", low):
        return Route("research", raw, force_web=True)

    if requires_fresh_data(raw) or re.search(r"\brestaurant\b", low):
        return Route("research", raw, force_web=True)

    if re.match(r"^(who|what|where|when|why|how)\b", low):
        return Route("research", raw, force_web=False)

    # Factual-looking statement: verify it on the web instead of trusting it.
    if re.search(r"\b(is|are|was|were|has|have|means|causes)\b", low):
        return Route("verify", raw, force_web=True)

    return Route("conversation", raw)
