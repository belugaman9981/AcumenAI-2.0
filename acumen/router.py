import re
from dataclasses import dataclass

@dataclass
class Route:
    kind: str
    query: str
    force_web: bool = False

GREETINGS = {"hello", "hi", "hey", "yo", "hiya"}
THANKS = {"thanks", "thank you", "thx"}
FAREWELLS = {"bye", "goodbye", "later", "cya"}

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

    if re.search(r"\b(homework|worksheet|assignment)\b", low):
        return Route("homework", raw, force_web=True)

    if re.search(r"\b(solve|calculate|evaluate)\b", low) and re.search(r"[0-9=+\-*/^x]", low):
        return Route("math", raw)

    if re.search(r"\b(find|search|look up|lookup|research|browse|scrape)\b", low):
        return Route("research", raw, force_web=True)

    if re.search(r"\b(flight|hotel|restaurant|price|weather|news|latest|current)\b", low):
        return Route("research", raw, force_web=True)

    if re.match(r"^(who|what|where|when|why|how)\b", low):
        return Route("research", raw, force_web=False)

    # Factual-looking statement: verify it on the web instead of trusting it.
    if re.search(r"\b(is|are|was|were|has|have|means|causes)\b", low):
        return Route("verify", raw, force_web=True)

    return Route("conversation", raw)
