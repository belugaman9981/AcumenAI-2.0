from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Plan:
    action: str
    argument: str = ""
    reason: str = ""

class Planner:
    def plan(self, user_input: str) -> Plan:
        text = user_input.strip()
        low = text.lower()
        if low.startswith("/calc "):
            return Plan("tool:calculator", text[6:].strip(), "Explicit calculator command")
        if low.startswith("/ingest "):
            return Plan("ingest_file", text[8:].strip(), "Explicit ingest command")
        if low.startswith("/remember "):
            return Plan("remember", text[10:].strip(), "Explicit memory command")
        if low.startswith("/forget "):
            return Plan("forget", text[8:].strip(), "Explicit forget command")
        if low.startswith("/memories"):
            return Plan("memories", text[len("/memories"):].strip(), "Inspect memory")
        if low == "/status":
            return Plan("status", "", "Status")
        if low == "/sources":
            return Plan("sources", "", "Sources")
        if low == "/help":
            return Plan("help", "", "Help")
        if low in {"/quit", "/exit"}:
            return Plan("quit", "", "Exit")
        if low.startswith("/learn "):
            return Plan("learn", text[7:].strip(), "Explicit learning")
        return Plan("chat", text, "General conversation")
