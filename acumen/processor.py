from pathlib import Path
from .research import WebResearcher
from .homework import solve_math
from .knowledge import KnowledgeStore
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

    def process(self, task_type, payload, session_id):
        query = payload.get("query", "").strip()

        # Also handle queued research jobs from clients with older routing code.
        if task_type == "time" or (
            task_type in {"research", "knowledge_query"} and is_time_request(query)
        ):
            return self.time_provider.from_text(query)

        if task_type == "knowledge_query":
            hit = None if requires_fresh_data(query) else self.knowledge.lookup(query)
            if hit:
                return {
                    "ok": True,
                    "answer": hit["answer"],
                    "sources": hit.get("sources", []),
                    "evidence": hit.get("evidence", []),
                    "confidence": hit.get("confidence", .5),
                    "from_knowledge": True,
                }
            task_type = "research"

        if task_type == "math":
            result = solve_math(query)
            if result:
                self.sessions.add_candidate(
                    session_id, self._candidate(query, result, "math")
                )
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
            if result.get("ok") and result.get("learnable", True) and not requires_fresh_data(query):
                self.sessions.add_candidate(
                    session_id, self._candidate(query, result, "homework")
                )
            return result

        if task_type in {"research", "verify"}:
            result = self.researcher.research(query)
            if result.get("ok") and result.get("learnable", True) and not requires_fresh_data(query):
                self.sessions.add_candidate(
                    session_id, self._candidate(query, result, task_type)
                )
            return result

        if task_type == "finalize_session":
            return {"ok": True, "finalize": True, "session_id": session_id}

        return {"ok": False, "answer": f"Unknown task type: {task_type}", "sources": []}
