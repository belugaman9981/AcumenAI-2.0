from pathlib import Path
from .router import route
from .task_queue import TaskQueue
from .processor import TaskProcessor
from .knowledge import KnowledgeStore
from .sessions import SessionStore

class AcumenClient:
    def __init__(self, mode, root: Path, config):
        self.mode = mode
        self.root = root
        self.config = config
        self.queue = TaskQueue(root)
        self.session_store = SessionStore(root)
        self.session_id = self.session_store.create()
        self.local_processor = TaskProcessor(root, config) if mode == "local" else None
        self.knowledge = KnowledgeStore(root)
        self.show_sources = True
        self.history = []
        self.last_question = None
        self.last_result = None

    def _execute(self, task_type, query):
        payload = {"query": query}

        if self.mode == "local":
            return self.local_processor.process(task_type, payload, self.session_id)

        task_id = self.queue.submit(task_type, payload, self.session_id)
        result = self.queue.wait(
            task_id,
            timeout=float(self.config["tasks"]["wait_seconds"]),
            poll_interval=float(self.config["tasks"]["poll_interval"]),
        )
        if result is None:
            return {
                "ok": False,
                "answer": (
                    "The local worker did not answer in time. "
                    "Make sure worker.py is running on your computer."
                ),
                "sources": [],
            }
        self.queue.consume(task_id)
        return result

    def _format(self, result):
        answer = result.get("answer", "No answer.")
        if not self.show_sources:
            return answer

        sources = result.get("sources", [])
        if sources:
            unique = []
            seen = set()
            for s in sources:
                url = s.get("url", "")
                if url in seen:
                    continue
                seen.add(url)
                unique.append(s)
            if unique:
                answer += "\n\nSources:"
                for s in unique[:5]:
                    answer += f"\n- {s.get('title','Source')}: {s.get('url','')}"
        return answer

    def chat(self, text):
        text = text.strip()
        if not text:
            return "Type a question, or use /examples for ideas."
        r = route(text)

        if r.kind == "greeting":
            return "Hi. What can I help you with?"
        if r.kind == "thanks":
            return "You're welcome."
        if r.kind == "farewell":
            return "See you."

        if r.kind == "command":
            low = text.lower().strip()
            if low == "/examples":
                return (
                    "Try one of these:\n"
                    "- Explain why the sky is blue\n"
                    "- What time is it in Vancouver?\n"
                    "- What is the weather in Paris?\n"
                    "- Solve 2*x + 3 = 11"
                )
            if low == "/history":
                if not self.history:
                    return "No questions yet. Use /examples for ideas."
                return "\n\n".join(f"You: {q}\nAcumen: {a}" for q, a in self.history)
            if low == "/again":
                return self.chat(self.last_question) if self.last_question else "Ask a question first, then use /again."
            if low == "/sources":
                sources = (self.last_result or {}).get("sources", [])
                return "\n".join(f"- {s.get('title', 'Source')}: {s.get('url', '')}" for s in sources) or "No sources for the last answer."
            if low == "/learning":
                items = (self.session_store.get(self.session_id) or {}).get("candidates", [])
                if not items:
                    return "No new learning to review yet."
                return "\n\n".join(f"{i}. {c['query']}\n{c['answer']}" for i, c in enumerate(items, 1)) + "\n\n/save to keep all, /discard to discard all."
            if low in {"/save", "/discard"}:
                return self._format(self._execute("session_learning", low[1:]))
            if low == "/status":
                return (
                    f"Mode: {self.mode}\n"
                    f"Session: {self.session_id}\n"
                    f"Storage root: {self.root}\n"
                    f"Permanent knowledge items: {len(self.knowledge.all())}\n"
                    f"Learning awaiting review: {len((self.session_store.get(self.session_id) or {}).get('candidates', []))}\n"
                    f"Sources: {'shown' if self.show_sources else 'hidden'}"
                )
            if low in {"/hide-source", "/hide-sources"}:
                self.show_sources = False
                return "Sources are now hidden."
            if low in {"/show-source", "/show-sources"}:
                self.show_sources = True
                return "Sources are now shown."
            if low == "/knowledge" or low.startswith("/knowledge "):
                search = text.split(None, 1)[1] if " " in low else ""
                items = self.knowledge.search(search, limit=30) if search else self.knowledge.all()
                if not items:
                    return "No matching saved knowledge." if search else "No permanent knowledge saved."
                return "\n".join(
                    f"{x['id']} | {x['query']} -> {x['answer'][:120]}"
                    for x in items[-30:]
                )
            if low.startswith("/delete "):
                item_id = text.split(None, 1)[1].strip()
                return "Deleted." if self.knowledge.delete(item_id) else "Knowledge ID not found."
            if low == "/help":
                return (
                    "Ask a question normally, or use:\n"
                    "/examples — starter questions\n"
                    "/history — last 30 questions and answers this session\n"
                    "/again — ask your last question again\n"
                    "/sources — sources for the last answer\n"
                    "/hide-source or /show-source — change source display\n"
                    "/knowledge [search words] — browse saved knowledge\n"
                    "/learning — review new learning\n"
                    "/save or /discard — keep or discard all new learning\n"
                    "/delete <id> — delete a saved item\n"
                    "/status — session details\n"
                    "/quit — exit the command line"
                )
            return "Unknown command. Type /help."

        if r.kind == "conversation":
            return (
                "I can look up the time in a city, research the web, get live weather, verify claims, solve supported math, "
                "and work on homework questions. Ask me what you want me to find or solve."
            )

        task_type = r.kind
        # The worker considers both saved and pending answers, including conflicts.
        if r.kind == "research" and not r.force_web:
            task_type = "knowledge_query"

        result = self._execute(task_type, r.query)
        self.last_question = text
        self.last_result = result
        answer = self._format(result)
        self.history.append((text, answer))
        self.history = self.history[-30:]
        return answer

    def close(self):
        if self.mode == "local":
            try:
                self.session_store.finalize_interactive(self.session_id, self.knowledge)
            finally:
                self.local_processor.close()
            return

        # Pi does not save knowledge. It only asks the local worker to finalize.
        task_id = self.queue.submit(
            "finalize_session",
            {"query": ""},
            self.session_id,
        )
        print(
            "\nAcumen: Session closed. Check the worker window on your local computer "
            "to choose whether to save what Acumen learned."
        )
