from pathlib import Path
from acumen.gate import classify_input
from acumen.claim import extract_claim
from acumen.graph import KnowledgeGraph
from acumen.reasoning import Reasoner
from acumen.tools import calculate
from acumen.verification_queue import VerificationQueue

def test_greeting():
    assert classify_input("hello").kind == "greeting"

def test_claim():
    c = extract_claim("Ottawa is the capital of Canada.")
    assert c.subject == "ottawa"
    assert c.relation == "capital_of"
    assert c.object == "canada"

def test_alias():
    c = extract_claim("Ottawa is the capital of USA.")
    assert c.object == "united states"

def test_calculator():
    assert calculate("2+3*4") == "14"

def test_graph(tmp_path: Path):
    g = KnowledgeGraph(tmp_path)
    g.add_verified("ottawa", "capital_of", "canada", 0.96, [])
    answers, facts = Reasoner(g).relation("canada", "capital_of")
    assert answers == ["ottawa"]

def test_queue(tmp_path: Path):
    q = VerificationQueue(tmp_path)
    c = extract_claim("Ottawa is the capital of Canada.")
    job_id = q.submit(c)
    assert (tmp_path / "verify_queue" / f"{job_id}.json").exists()
