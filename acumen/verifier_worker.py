from pathlib import Path
import argparse
import json
import time
import shutil
from .storage import atomic_json_write
from .web_verifier import WikipediaVerifier

def process_job(job_path, root, verifier):
    try:
        payload = json.loads(job_path.read_text(encoding="utf-8"))
        job_id = payload["job_id"]
        claim = payload["claim"]
        result = verifier.verify(claim).to_dict()
        result["job_id"] = job_id

        results_dir = root / "verify_results"
        processed_dir = root / "verify_processed"
        results_dir.mkdir(parents=True, exist_ok=True)
        processed_dir.mkdir(parents=True, exist_ok=True)

        atomic_json_write(results_dir / f"{job_id}.json", result)
        job_path.replace(processed_dir / job_path.name)

        print(
            f"[{job_id[:8]}] {claim['raw']} -> "
            f"{result['status']} ({result['confidence']:.2f})"
        )
    except Exception as e:
        print(f"Failed job {job_path.name}: {type(e).__name__}: {e}")

def main():
    parser = argparse.ArgumentParser(description="AcumenAI Windows web-verification worker")
    parser.add_argument("--root", default="data", help="Shared Acumen data directory")
    parser.add_argument("--once", action="store_true", help="Process queued jobs once and exit")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    queue = root / "verify_queue"
    queue.mkdir(parents=True, exist_ok=True)

    verifier = WikipediaVerifier()
    print(f"Acumen verifier watching: {queue}")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            jobs = sorted(queue.glob("*.json"))
            for job in jobs:
                process_job(job, root, verifier)

            if args.once:
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nVerifier stopped.")
