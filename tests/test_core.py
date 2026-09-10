from pathlib import Path
from tempfile import TemporaryDirectory
from acumen.router import route
from acumen.knowledge import KnowledgeStore
from acumen.sessions import SessionStore
from acumen.task_queue import TaskQueue
from acumen.homework import solve_math

def test_router():
    assert route("hello").kind == "greeting"
    assert route("find me flights from YVR to PEK").kind == "research"
    assert route("help me with my homework: solve 2*x + 3 = 11").kind == "homework"

def test_knowledge():
    with TemporaryDirectory() as d:
        store = KnowledgeStore(Path(d))
        item = store.add({
            "query":"capital of canada",
            "answer":"Ottawa",
            "sources":[],
            "confidence":.9,
        })
        assert store.search("canada capital")[0]["answer"] == "Ottawa"
        assert store.delete(item["id"])

def test_queue():
    with TemporaryDirectory() as d:
        q = TaskQueue(Path(d))
        tid = q.submit("research", {"query":"test"}, "session")
        assert (Path(d)/"task_queue"/f"{tid}.json").exists()

def test_math():
    r = solve_math("solve 2*x + 3 = 11")
    assert r and "4" in r["answer"]
