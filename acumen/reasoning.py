from collections import deque

class Reasoner:
    def __init__(self, g, max_depth=4):
        self.g = g
        self.max_depth = max_depth

    def relation(self, subject, relation):
        # Most relations are stored subject -> relation -> object.
        # capital_of is linguistically stored as:
        #   ottawa --capital_of--> canada
        # but queried as "capital of canada", so reverse that lookup.
        if relation == "capital_of":
            facts = self.g.query(relation=relation, obj=subject)
            return ([f["subject"] for f in facts],
                    [f["id"] for f in facts],
                    facts)

        facts = self.g.query(subject=subject, relation=relation)
        return ([f["object"] for f in facts],
                [f["id"] for f in facts],
                facts)

    def entails(self, subject, relation, obj):
        facts = self.g.query(subject=subject, relation=relation, obj=obj)
        if facts:
            return True, [facts[0]], [facts[0]["id"]]

        if relation != "is_a":
            return False, [], []

        q = deque([(subject, [], 0)])
        seen = {subject}

        while q:
            current, path, depth = q.popleft()
            if depth >= self.max_depth:
                continue

            for fact in self.g.query(subject=current, relation="is_a"):
                new_path = path + [fact]

                if fact["object"] == obj:
                    return True, new_path, [x["id"] for x in new_path]

                if fact["object"] not in seen:
                    seen.add(fact["object"])
                    q.append((fact["object"], new_path, depth + 1))

        return False, [], []

    def explain(self, path):
        if not path:
            return "I do not have a proof for that."
        return "\n".join(
            f"{i}. {f['subject']} --{f['relation']}--> {f['object']}"
            for i, f in enumerate(path, 1)
        )
