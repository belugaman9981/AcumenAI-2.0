from .extractor import extract_triples

class Learner:
    def __init__(self, memory, graph):
        self.memory = memory
        self.graph = graph

    def learn(self, text, source="user", confidence=0.85):
        triples = extract_triples(text)
        facts = []
        for t in triples:
            facts.append(self.graph.add(
                t.subject, t.relation, t.object,
                source=source,
                confidence=min(confidence, t.confidence),
            ))
        self.memory.add(
            text,
            kind="semantic" if triples else "episodic",
            source=source,
            confidence=confidence if triples else 0.55,
            metadata={"fact_ids": [f["id"] for f in facts]},
        )
        return triples, facts

    def reinforce(self, memory_ids=None, fact_ids=None):
        self.memory.touch(memory_ids or [])
        self.graph.touch(fact_ids or [])
