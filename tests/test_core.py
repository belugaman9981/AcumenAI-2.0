from acumen.memory import MemoryStore
from acumen.graph import KnowledgeGraph
from acumen.learner import Learner
from acumen.reasoning import Reasoner
def test_capital(tmp_path):
    m=MemoryStore(tmp_path); g=KnowledgeGraph(tmp_path); l=Learner(m,g); l.learn('Ottawa is the capital of Canada.')
    a,_,_=Reasoner(g).relation('canada','capital_of'); assert a==['ottawa']
def test_inference(tmp_path):
    m=MemoryStore(tmp_path); g=KnowledgeGraph(tmp_path); l=Learner(m,g); l.learn('Whales are a mammals.'); l.learn('All mammals are warm-blooded.')
    ok,_,_=Reasoner(g).entails('whales','is_a','warm-blooded'); assert ok
