from pathlib import Path
from urllib.parse import urlsplit
from .research import WebResearcher
from .homework import solve_math
from .knowledge import KnowledgeStore, clean_candidate, select_answer
from .sessions import SessionStore
from .weather import weather_from_text
from .time_service import TimeProvider, is_time_request
from .router import requires_fresh_data

class TaskProcessor:
    def __init__(self, root: Path, config):
        self.root = root
        self.config = config
        self.knowledge = KnowledgeStore(root)
        self.sessions = SessionStore(root)
        self.researcher = WebResearcher(config["research"])
        self.time_provider = TimeProvider(timeout=config["research"]["request_timeout"])

    def close(self):
        self.researcher.close()

    def _candidate(self, query, result, kind):
        candidate = {
            "query": query,
            "answer": result.get("answer", ""),
            "sources": result.get("sources", []),
            "confidence": result.get("confidence", .5),
            "kind": kind,
        }
        if result.get("evidence"):
            candidate["evidence"] = result["evidence"]
        return candidate

    def _learn(self, query, result, kind, session_id):
        """Only supported, sufficiently confident stable answers enter review."""
        if not query or not result.get("ok") or not result.get("learnable", True):
            return
        if requires_fresh_data(query):
            return
        candidate = clean_candidate(self._candidate(query, result, kind))
        supported = False
        for source in candidate["sources"]:
            try:
                url = urlsplit(source.get("url", ""))
                supported |= url.scheme in {"http", "https"} and bool(url.hostname)
                supported |= kind in {"math", "homework"} and source.get("url") == "local://sympy"
            except (TypeError, ValueError):
                continue
        if candidate["answer"] and candidate["confidence"] >= .6 and supported:
            self.sessions.add_candidate(session_id, candidate)

    def process(self, task_type, payload, session_id):
        query = payload.get("query", "").strip()

        # Also handle queued research jobs from clients with older routing code.
        if task_type == "time" or (
            task_type in {"research", "knowledge_query"} and is_time_request(query)
        ):
            return self.time_provider.from_text(query)

        if task_type == "knowledge_query":
            pending = self.sessions.get(session_id) or {}
            hit = select_answer(
                self.knowledge.all() + pending.get("candidates", []), query,
            )
            if hit:
                self.knowledge.record_use(hit.get("id"))
                return {
                    "ok": True,
                    "answer": hit["answer"],
                    "sources": hit.get("sources", []),
                    "evidence": hit.get("evidence", []),
                    "confidence": hit.get("confidence", .5),
                    "from_knowledge": bool(hit.get("id")),
                    "from_session": not bool(hit.get("id")),
                }
            task_type = "research"

        if task_type == "math":
            result = solve_math(query)
            if result:
                self._learn(query, result, "math", session_id)
                return result
            task_type = "research"

        if task_type == "weather":
            result = weather_from_text(
                query,
                timeout=self.config["research"]["request_timeout"],
            )
            # Weather is volatile: return it, but do not learn it permanently.
            return result

        if task_type == "homework":
            # Try symbolic math first, then research.
            result = solve_math(query)
            if result is None:
                result = self.researcher.research(query)
            self._learn(query, result, "homework", session_id)
            return result

        if task_type in {"research", "verify"}:
            result = self.researcher.research(query)
            self._learn(query, result, task_type, session_id)
            return result

        if task_type == "finalize_session":
            return {"ok": True, "finalize": True, "session_id": session_id}

        return {"ok": False, "answer": f"Unknown task type: {task_type}", "sources": []}
