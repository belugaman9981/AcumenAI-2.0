from pathlib import Path
import json
import time
import uuid
from .storage import atomic_json_write, utc_now

class VerificationQueue:
    def __init__(self, root: Path):
        self.queue_dir = root / "verify_queue"
        self.results_dir = root / "verify_results"
        self.archive_dir = root / "verify_archive"
        for p in (self.queue_dir, self.results_dir, self.archive_dir):
            p.mkdir(parents=True, exist_ok=True)

    def submit(self, claim):
        job_id = str(uuid.uuid4())
        payload = {
            "job_id": job_id,
            "created_at": utc_now(),
            "claim": {
                "subject": claim.subject,
                "relation": claim.relation,
                "object": claim.object,
                "raw": claim.raw,
            },
        }
        atomic_json_write(self.queue_dir / f"{job_id}.json", payload)
        return job_id

    def wait_for_result(self, job_id, timeout=15, poll_interval=0.25):
        path = self.results_dir / f"{job_id}.json"
        end = time.time() + timeout
        while time.time() < end:
            if path.exists():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass
            time.sleep(poll_interval)
        return None

    def consume_result(self, job_id):
        path = self.results_dir / f"{job_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        target = self.archive_dir / f"{job_id}.result.json"
        try:
            path.replace(target)
        except OSError:
            pass
        return data
