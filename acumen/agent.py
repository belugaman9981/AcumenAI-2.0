from __future__ import annotations
from pathlib import Path
from .memory import MemoryStore
from .conversations import ConversationStore
from .knowledge import KnowledgeIngestor
from .planner import Planner
from .learner import Learner
from .model import RuleBasedBackend
from .tools import build_tools

class AcumenAgent:
    def __init__(self, config: dict):
        self.config = config
        root = Path(config["storage"]["root"]).expanduser()
        root.mkdir(parents=True, exist_ok=True)

        self.memory = MemoryStore(root)
        self.conversations = ConversationStore(root)
        self.knowledge = KnowledgeIngestor(self.memory)
        self.planner = Planner()
        self.learner = Learner(self.memory)
        self.tools = build_tools()
        self.model = RuleBasedBackend()
        self.root = root

    def status(self) -> str:
        memories = self.memory.all()
        turns = self.conversations.recent(10_000)
        return (
            f"AcumenAI 2.0 status\n"
            f"Storage: {self.root}\n"
            f"Memories: {len(memories)}\n"
            f"Conversation turns: {len(turns)}\n"
            f"Model backend: {self.config['model']['backend']}"
        )

    def help(self) -> str:
        return (
            "/help\n/status\n/remember <text>\n/forget <memory_id>\n"
            "/memories [query]\n/learn <text>\n/ingest <path>\n"
            "/calc <expression>\n/sources\n/quit"
        )

    def handle(self, user_input: str) -> tuple[str, bool]:
        plan = self.planner.plan(user_input)

        if plan.action == "quit":
            return "Shutting down.", True
        if plan.action == "help":
            return self.help(), False
        if plan.action == "status":
            return self.status(), False
        if plan.action == "remember":
            m = self.memory.add(plan.argument, kind="semantic", source="user", confidence=0.9)
            return f"Stored memory {m['id']}: {m['text']}", False
        if plan.action == "forget":
            ok = self.memory.delete(plan.argument)
            return ("Memory deleted." if ok else "Memory ID not found."), False
        if plan.action == "memories":
            items = self.memory.search(plan.argument) if plan.argument else self.memory.all()[-20:]
            if not items:
                return "No matching memories.", False
            return "\n".join(
                f"{m['id']} | {m['kind']} | {m['text']}"
                + (f" | score={m['score']}" if "score" in m else "")
                for m in items
            ), False
        if plan.action == "learn":
            items = self.knowledge.ingest_text(plan.argument, source="manual")
            return f"Learned {len(items)} knowledge chunk(s).", False
        if plan.action == "ingest_file":
            try:
                items = self.knowledge.ingest_file(plan.argument)
                return f"Ingested {len(items)} chunk(s) from {plan.argument}.", False
            except Exception as e:
                return f"Ingest failed: {e}", False
        if plan.action.startswith("tool:"):
            name = plan.action.split(":", 1)[1]
            result = self.tools[name].run(plan.argument)
            return result.output, False
        if plan.action == "sources":
            sources = sorted(set(m.get("source", "unknown") for m in self.memory.all()))
            return ("\n".join(sources) if sources else "No sources stored."), False

        self.conversations.add_turn("user", user_input)
        max_results = int(self.config["memory"]["max_retrieval_results"])
        min_score = float(self.config["memory"]["min_score"])
        memories = self.memory.search(user_input, max_results, min_score)
        recent = self.conversations.recent(12)

        response = self.model.generate(user_input, memories, recent)
        self.conversations.add_turn("assistant", response, {"used_memory_ids": [m["id"] for m in memories]})

        if self.config["agent"]["auto_learn_user_statements"]:
            self.learner.maybe_learn_user_statement(user_input)
        if self.config["agent"]["reflection_enabled"]:
            self.learner.reflect(user_input, response, memories)

        return response, False
