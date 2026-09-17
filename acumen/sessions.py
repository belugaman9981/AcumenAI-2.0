from pathlib import Path
import hashlib
import json
from .storage import atomic_write_json, read_json, utc_now, new_id
from .knowledge import clean_candidate, candidate_fingerprint, merge_candidate


DECLINED_LEARNING_LIMIT = 256


def _fingerprint_digest(fingerprint):
    serialized = json.dumps(fingerprint, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def candidate_review_id(candidate):
    """Identify the exact pending revision, including its evidence and metadata."""
    serialized = json.dumps(candidate, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class PendingLearningChanged(LookupError):
    """The selected learning item has changed or is no longer pending."""


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
        data = dict(data, updated_at=utc_now())
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
        if _fingerprint_digest(key) in data.get("declined_fingerprints", []):
            return
        for index, old in enumerate(data["candidates"]):
            if candidate_fingerprint(old) == key:
                merged = merge_candidate(old, candidate)
                # merge_candidate always pins "researched_at" (even to None) so
                # that KnowledgeStore's later "updated_at" stamp can never be
                # mistaken for a fresh research date. Session candidates never
                # get that separate stamp, so a bare None placeholder here isn't
                # a real change -- drop it before deciding whether to persist,
                # so re-learning the exact same fact doesn't force a disk write.
                if merged.get("researched_at") is None and "researched_at" not in old:
                    merged.pop("researched_at", None)
                if merged != old:
                    candidates = list(data["candidates"])
                    candidates[index] = merged
                    self._write(session_id, dict(data, candidates=candidates))
                return
        self._write(session_id, dict(data, candidates=data["candidates"] + [candidate]))

    def clear(self, session_id):
        p = self._path(session_id)
        if p.exists():
            p.unlink()

    def resolve_pending(self, session_id, action, knowledge_store, item_id=None):
        """Save or discard current candidates while keeping the session open."""
        if action not in {"save", "discard"}:
            raise ValueError("Choose save or discard.")
        if item_id is not None and (not isinstance(item_id, str) or not item_id.strip()):
            raise ValueError("item_id must be nonempty text.")
        data = self.get(session_id)
        candidates = (data or {}).get("candidates", [])
        selected_index = None
        if item_id is not None:
            selected_index = next((index for index, candidate in enumerate(candidates)
                                   if candidate_review_id(candidate) == item_id), None)
            if selected_index is None:
                raise PendingLearningChanged("This learning item changed or was already reviewed. Refresh the learning list and try again.")
            selected = [candidates[selected_index]]
        else:
            selected = candidates
        if not selected:
            return 0
        if action == "save":
            knowledge_store.add_many(selected)
        # Keep candidates available for retry if saving raises an error.
        remaining = [] if item_id is None else [
            candidate for index, candidate in enumerate(candidates) if index != selected_index
        ]
        updated = dict(data, candidates=remaining)
        if action == "discard":
            # Remember review decisions only for this session, without retaining
            # discarded answers. Alternative answers to the question stay eligible.
            declined = dict.fromkeys(data.get("declined_fingerprints", []))
            for candidate in selected:
                digest = _fingerprint_digest(candidate_fingerprint(candidate))
                declined.pop(digest, None)
                declined[digest] = None
            updated["declined_fingerprints"] = list(declined)[-DECLINED_LEARNING_LIMIT:]
        self._write(session_id, updated)
        return len(selected)

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
