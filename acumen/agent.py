from pathlib import Path
from .gate import classify_input
from .claim import extract_claim, Claim
from .memory import MemoryStore
from .graph import KnowledgeGraph
from .verification_queue import VerificationQueue
from .reasoning import Reasoner
from .query import parse_relation_query, parse_boolean_query
from .response import greeting, thanks, farewell, verification_message, titleish
from .tools import calculate

class AcumenAgent:
    def __init__(self, config):
        self.config = config
        self.root = Path(config["storage"]["root"]).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

        self.memory = MemoryStore(self.root)
        self.graph = KnowledgeGraph(self.root)
        self.verify_queue = VerificationQueue(self.root)
        self.reasoner = Reasoner(self.graph, int(config["reasoning"]["max_depth"]))

    def status(self):
        return (
            "AcumenAI 2.0 v0.3.0\n"
            f"Storage: {self.root}\n"
            f"Trusted facts: {len(self.graph.all())}\n"
            f"Memories: {len(self.memory.all())}\n"
            f"Web verification: {'enabled' if self.config['verification']['enabled'] else 'disabled'}\n"
            "LLM: none"
        )

    def help(self):
        return (
            "/help\n/status\n/facts\n/memories [query]\n"
            "/verify <claim>\n/why <question>\n/calc <expression>\n/quit"
        )

    def _verify_claim(self, claim):
        if not self.config["verification"]["enabled"]:
            return "Web verification is disabled."

        job_id = self.verify_queue.submit(claim)
        result = self.verify_queue.wait_for_result(
            job_id,
            timeout=float(self.config["verification"]["wait_seconds"]),
            poll_interval=float(self.config["verification"]["poll_interval"]),
        )

        if result is None:
            return (
                "I queued that claim for verification, but the verifier did not answer in time. "
                "Make sure verifier_worker.py is running on the Windows PC."
            )

        self.verify_queue.consume_result(job_id)

        min_conf = float(self.config["verification"]["minimum_confidence"])
        if result.get("status") == "verified" and float(result.get("confidence", 0)) >= min_conf:
            subject = result.get("corrected_subject") or result["claimed_subject"]
            obj = result.get("corrected_object") or result["claimed_object"]
            self.graph.add_verified(
                subject,
                result["relation"],
                obj,
                result["confidence"],
                result.get("evidence", []),
            )

        # Keep verification outcome as episodic evidence, not trusted fact.
        self.memory.add(
            claim.raw,
            kind="verification",
            source="web_verifier",
            confidence=float(result.get("confidence", 0)),
            metadata={
                "verification_status": result.get("status"),
                "evidence": result.get("evidence", []),
            },
        )
        return verification_message(result)

    def handle(self, text):
        raw = text.strip()
        low = raw.lower()

        if low in {"/quit", "/exit"}:
            return "Shutting down.", True
        if low == "/help":
            return self.help(), False
        if low == "/status":
            return self.status(), False
        if low == "/facts":
            facts = self.graph.all()
            if not facts:
                return "No trusted facts yet.", False
            return "\n".join(
                f"{f['subject']} --{f['relation']}--> {f['object']} "
                f"(confidence {f['confidence']:.2f})"
                for f in facts[-50:]
            ), False
        if low.startswith("/memories"):
            q = raw[len("/memories"):].strip()
            items = self.memory.search(q) if q else self.memory.all()[-20:]
            if not items:
                return "No matching memories.", False
            return "\n".join(f"{m['kind']}: {m['text']}" for m in items), False
        if low.startswith("/calc "):
            try:
                return calculate(raw[6:].strip()), False
            except Exception as e:
                return f"Calculator error: {e}", False
        if low.startswith("/verify "):
            claim = extract_claim(raw[8:].strip())
            if not claim:
                return "I couldn't convert that sentence into a structured claim yet.", False
            return self._verify_claim(claim), False
        if low.startswith("/why "):
            q = raw[5:].strip()
            b = parse_boolean_query(q)
            if b:
                found, path = self.reasoner.entails(*b)
                return self.reasoner.explain(path), False
            r = parse_relation_query(q)
            if r:
                answers, path = self.reasoner.relation(*r)
                return self.reasoner.explain(path), False
            return "I couldn't parse that explanation query.", False

        gate = classify_input(raw)

        if gate.kind == "greeting":
            return greeting(), False
        if gate.kind == "thanks":
            return thanks(), False
        if gate.kind == "farewell":
            return farewell(), False

        # First answer trusted factual questions from the Pi's graph.
        relation_q = parse_relation_query(raw)
        if relation_q:
            subject, relation = relation_q
            answers, facts = self.reasoner.relation(subject, relation)
            if answers:
                answer = answers[0]
                if relation == "capital_of":
                    return f"The capital of {titleish(subject)} is {titleish(answer)}.", False
                return f"{titleish(subject)} {relation.replace('_', ' ')} {titleish(answer)}.", False
            return "I don't have a verified answer for that yet.", False

        boolean_q = parse_boolean_query(raw)
        if boolean_q:
            found, path = self.reasoner.entails(*boolean_q)
            if found:
                return "Yes. I can support that from my verified knowledge.", False
            return "I can't prove that from my verified knowledge.", False

        # Claims go through web verification before entering trusted knowledge.
        if gate.kind == "claim":
            claim = extract_claim(raw)
            if claim:
                return self._verify_claim(claim), False
            self.memory.add(raw, kind="conversation", confidence=0.25)
            return "I understood that as a statement, but I couldn't structure it well enough to verify it yet.", False

        # Ordinary conversation is not treated as factual knowledge.
        self.memory.add(raw, kind="conversation", confidence=0.20)
        return "I don't have a conversational rule for that yet.", False
