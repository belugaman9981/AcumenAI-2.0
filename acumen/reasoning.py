from collections import deque

class Reasoner:
    def __init__(self, graph, max_depth=4):
        self.graph = graph
        self.max_depth = max_depth

    def relation(self, subject, relation):
        if relation == "capital_of":
            facts = self.graph.query(relation=relation, obj=subject)
            return [f["subject"] for f in facts], facts
        facts = self.graph.query(subject=subject, relation=relation)
        return [f["object"] for f in facts], facts

    def entails(self, subject, relation, obj):
        direct = self.graph.query(subject=subject, relation=relation, obj=obj)
        if direct:
            return True, direct
        if relation != "is_a":
            return False, []

        queue = deque([(subject, [], 0)])
        seen = {subject}
        while queue:
            current, path, depth = queue.popleft()
            if depth >= self.max_depth:
                continue
            for fact in self.graph.query(subject=current, relation="is_a"):
                new_path = path + [fact]
                if fact["object"] == obj:
                    return True, new_path
                if fact["object"] not in seen:
                    seen.add(fact["object"])
                    queue.append((fact["object"], new_path, depth + 1))
        return False, []

    def explain(self, path):
        if not path:
            return "I do not have a proof for that."
        return "\n".join(
            f"{i}. {f['subject']} --{f['relation']}--> {f['object']}"
            for i, f in enumerate(path, 1)
        )
