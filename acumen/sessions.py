from pathlib import Path
from .storage import atomic_write_json, read_json, utc_now, new_id

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
        data = self.get(session_id)
        if data is None:
            data = {
                "session_id": session_id,
                "created_at": utc_now(),
                "candidates": [],
            }
        # Avoid saving identical candidates repeatedly.
        key = (candidate.get("query"), candidate.get("answer"))
        for old in data["candidates"]:
            if (old.get("query"), old.get("answer")) == key:
                return
        data["candidates"].append(candidate)
        self._write(session_id, data)

    def clear(self, session_id):
        p = self._path(session_id)
        if p.exists():
            p.unlink()

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
            for c in candidates:
                knowledge_store.add(c)
                saved += 1
        elif choice == "r":
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
                    knowledge_store.add(c)
                    saved += 1

        self.clear(session_id)
        print(f"Saved {saved} item(s). Discarded {len(candidates)-saved}.")
