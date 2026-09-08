from pathlib import Path
import time
from .storage import atomic_write_json, read_json, new_id, utc_now

class TaskQueue:
    def __init__(self, root: Path):
        self.queue = root / "task_queue"
        self.results = root / "task_results"
        self.archive = root / "task_archive"
        for p in (self.queue, self.results, self.archive):
            p.mkdir(parents=True, exist_ok=True)

    def submit(self, task_type, payload, session_id):
        task_id = new_id()
        atomic_write_json(self.queue / f"{task_id}.json", {
            "task_id": task_id,
            "task_type": task_type,
            "payload": payload,
            "session_id": session_id,
            "created_at": utc_now(),
        })
        return task_id

    def wait(self, task_id, timeout=45, poll_interval=.25):
        path = self.results / f"{task_id}.json"
        end = time.time() + timeout
        while time.time() < end:
            if path.exists():
                result = read_json(path, None)
                if result is not None:
                    return result
            time.sleep(poll_interval)
        return None

    def consume(self, task_id):
        path = self.results / f"{task_id}.json"
        if path.exists():
            try:
                path.replace(self.archive / f"{task_id}.result.json")
            except OSError:
                pass
