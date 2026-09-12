from pathlib import Path
from .storage import atomic_write_json, read_json, utc_now, new_id
from .knowledge import clean_candidate, candidate_fingerprint, merge_candidate

class SessionStore:
    def __init__(self, root: Path):
        self.dir = root / "sessions"
        self.dir.mkdir(parents=True, exist_ok=True)

    def create(self):
        session_id = new_id()
        self._write(session_id, {
            "session_id": session_id,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "candidates": [],
        })
        return session_id

    def _path(self, session_id):
        return self.dir / f"{session_id}.json"

    def _write(self, session_id, data):
        data["updated_at"] = utc_now()
        atomic_write_json(self._path(session_id), data)

    def get(self, session_id):
        return read_json(self._path(session_id), None)

    def add_candidate(self, session_id, candidate):
        candidate = clean_candidate(candidate)
        if not candidate.get("query") or not candidate.get("answer") or not candidate.get("learnable", True):
            return
        data = self.get(session_id)
        if data is None:
            data = {
                "session_id": session_id,
                "created_at": utc_now(),
                "candidates": [],
            }
        # Merge repeat learning without losing evidence from earlier sources.
        key = candidate_fingerprint(candidate)
        for index, old in enumerate(data["candidates"]):
            if candidate_fingerprint(old) == key:
                merged = merge_candidate(old, candidate)
                if merged != old:
                    data["candidates"][index] = merged
                    self._write(session_id, data)
                return
        data["candidates"].append(candidate)
        self._write(session_id, data)

    def clear(self, session_id):
        p = self._path(session_id)
        if p.exists():
            p.unlink()

    def resolve_pending(self, session_id, action, knowledge_store):
        """Save or discard current candidates while keeping the session open."""
        if action not in {"save", "discard"}:
            raise ValueError("Choose save or discard.")
        data = self.get(session_id)
        candidates = (data or {}).get("candidates", [])
        if not candidates:
            return 0
        if action == "save":
            knowledge_store.add_many(candidates)
        # Keep candidates available for retry if saving raises an error.
        data["candidates"] = []
        self._write(session_id, data)
        return len(candidates)

    def finalize_interactive(self, session_id, knowledge_store):
        data = self.get(session_id)
        if not data or not data.get("candidates"):
            self.clear(session_id)
            print(f"[session {session_id[:8]}] Nothing new to save.")
            return

        candidates = data["candidates"]
        print(f"\nAcumen session {session_id[:8]} ended.")
        print(f"{len(candidates)} candidate learning item(s) are waiting.")
        print("[S]ave all  [R]eview one-by-one  [D]iscard")
        choice = input("Choice: ").strip().lower()[:1] or "d"

        saved = 0
        if choice == "s":
            knowledge_store.add_many(candidates)
            saved = len(candidates)
        elif choice == "r":
            selected = []
            for i, c in enumerate(candidates, 1):
                print(f"\n[{i}/{len(candidates)}]")
                print("Question:", c.get("query"))
                print("Answer:", c.get("answer"))
                sources = c.get("sources", [])
                if sources:
                    print("Sources:")
                    for s in sources[:5]:
                        print(" -", s.get("title") or s.get("url"), s.get("url", ""))
                keep = input("Save this? [y/N]: ").strip().lower()
                if keep == "y":
                    selected.append(c)
            knowledge_store.add_many(selected)
            saved = len(selected)

        self.clear(session_id)
        print(f"Saved {saved} item(s). Discarded {len(candidates)-saved}.")
