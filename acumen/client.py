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

    @staticmethod
    def _format(result):
        answer = result.get("answer", "No answer.")
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
        r = route(text)

        if r.kind == "greeting":
            return "Hi. What can I help you with?"
        if r.kind == "thanks":
            return "You're welcome."
        if r.kind == "farewell":
            return "See you."

        if r.kind == "command":
            low = text.lower().strip()
            if low == "/status":
                return (
                    f"Mode: {self.mode}\n"
                    f"Session: {self.session_id}\n"
                    f"Storage root: {self.root}\n"
                    f"Permanent knowledge items: {len(self.knowledge.all())}"
                )
            if low == "/knowledge":
                items = self.knowledge.all()
                if not items:
                    return "No permanent knowledge saved."
                return "\n".join(
                    f"{x['id']} | {x['query']} -> {x['answer'][:120]}"
                    for x in items[-30:]
                )
            if low.startswith("/delete "):
                item_id = text.split(None, 1)[1].strip()
                return "Deleted." if self.knowledge.delete(item_id) else "Knowledge ID not found."
            if low == "/help":
                return (
                    "/status\n/knowledge\n/delete <id>\n/quit\n"
                    "Or ask any web/homework/research question."
                )
            return "Unknown command. Type /help."

        if r.kind == "conversation":
            return (
                "I can research things on the web, verify claims, solve supported math, "
                "and work on homework questions. Ask me what you want me to find or solve."
            )

        task_type = r.kind
        # Non-forced factual questions can reuse local knowledge first.
        if r.kind == "research" and not r.force_web:
            hits = self.knowledge.search(r.query)
            if hits and hits[0]["score"] >= .65:
                return self._format({
                    "answer": hits[0]["answer"],
                    "sources": hits[0].get("sources", []),
                })

        result = self._execute(task_type, r.query)
        return self._format(result)

    def close(self):
        if self.mode == "local":
            self.session_store.finalize_interactive(self.session_id, self.knowledge)
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
