from pathlib import Path
import argparse
import time
from .config import load_config
from .processor import TaskProcessor
from .storage import read_json, atomic_write_json
from .knowledge import KnowledgeStore
from .sessions import SessionStore

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument(
        "--save-policy",
        choices=["ask", "always", "never"],
        default="ask",
        help="What to do with candidate learning when a Pi session ends.",
    )
    args = ap.parse_args()

    cfg = load_config(args.config)
    root = Path(args.root).expanduser().resolve()
    processor = TaskProcessor(root, cfg)
    knowledge = KnowledgeStore(root)
    sessions = SessionStore(root)

    queue = root / "task_queue"
    results = root / "task_results"
    processed = root / "task_processed"
    for p in (queue, results, processed):
        p.mkdir(parents=True, exist_ok=True)

    print(f"Acumen local worker watching: {queue}")
    print("Web scraping and permanent storage happen on this computer.")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            for path in sorted(queue.glob("*.json")):
                job = read_json(path, None)
                if not job:
                    continue
                task_id = job["task_id"]
                task_type = job["task_type"]
                session_id = job["session_id"]

                try:
                    if task_type == "finalize_session":
                        if args.save_policy == "ask":
                            sessions.finalize_interactive(session_id, knowledge)
                        elif args.save_policy == "always":
                            data = sessions.get(session_id) or {"candidates":[]}
                            for c in data["candidates"]:
                                knowledge.add(c)
                            sessions.clear(session_id)
                        else:
                            sessions.clear(session_id)

                        result = {"ok": True, "answer": "Session finalized on local computer."}
                    else:
                        result = processor.process(
                            task_type, job.get("payload", {}), session_id
                        )
                except Exception as e:
                    result = {
                        "ok": False,
                        "answer": f"Worker error: {type(e).__name__}: {e}",
                        "sources": [],
                    }

                result["task_id"] = task_id
                atomic_write_json(results / f"{task_id}.json", result)
                try:
                    path.replace(processed / path.name)
                except OSError:
                    pass

            time.sleep(.35)
    except KeyboardInterrupt:
        print("\nWorker stopped.")
