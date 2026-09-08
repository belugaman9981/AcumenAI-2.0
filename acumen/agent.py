from pathlib import Path
from .memory import MemoryStore
from .graph import KnowledgeGraph
from .learner import Learner
from .reasoning import Reasoner
from .query import relation_query,boolean_query
from .tools import calculate
class Agent:
    def __init__(self,cfg):
        self.cfg=cfg; self.root=Path(cfg['storage']['root']).expanduser(); self.root.mkdir(parents=True,exist_ok=True)
        self.m=MemoryStore(self.root); self.g=KnowledgeGraph(self.root); self.l=Learner(self.m,self.g); self.r=Reasoner(self.g,int(cfg['reasoning']['max_depth'])); self.last_m=[]; self.last_f=[]
    def status(self): return f"AcumenAI 2.0 v0.2.1\nStorage: {self.root}\nMemories: {len(self.m.all())}\nFacts: {len(self.g.all())}\nLLM: none\nReasoning: symbolic"
    def handle(self,t):
        x=t.strip(); low=x.lower()
        if low in {'/quit','/exit'}:return 'Shutting down.',True
        if low=='/help':return '/status /remember /forget /memories /learn /facts /why /calc /feedback good /quit',False
        if low=='/status':return self.status(),False
        if low.startswith('/remember '):self.m.add(x[10:].strip(),confidence=.9);return 'Stored.',False
        if low.startswith('/forget '):return ('Memory deleted.' if self.m.delete(x[8:].strip()) else 'Memory ID not found.'),False
        if low.startswith('/memories'):
            q=x[len('/memories'):].strip(); a=self.m.search(q) if q else self.m.all()[-20:]; return ('No matching memories.' if not a else '\n'.join(f"{m['id']} | {m['text']}" for m in a)),False
        if low.startswith('/learn '):
            tri,_,_=self.l.learn(x[7:].strip(),'manual',.95); return ('Learned: '+'; '.join(f'{s} --{r}--> {o}' for s,r,o in tri)) if tri else "Stored, but I couldn't extract a structured fact.",False
        if low.startswith('/facts'):
            q=x[len('/facts'):].strip().lower(); fs=self.g.all(); fs=[f for f in fs if not q or q in f['subject'] or q in f['relation'] or q in f['object']]; return ('No matching facts.' if not fs else '\n'.join(f"{f['subject']} --{f['relation']}--> {f['object']}" for f in fs[-50:])),False
        if low.startswith('/calc '):
            try:return calculate(x[6:].strip()),False
            except Exception as e:return f'Calculator error: {e}',False
        if low.startswith('/feedback '):
            if x[10:].strip().lower()=='good':self.l.reinforce(self.last_m,self.last_f);return 'Reinforced the knowledge used in my previous answer.',False
            return 'Feedback recorded.',False
        if low.startswith('/why '):
            b=boolean_query(x[5:].strip())
            if b:
                ok,path,ids=self.r.entails(*b);return self.r.explain(path),False
            return "I couldn't parse that explanation query yet.",False
        rq=relation_query(x)
        if rq:
            s,r=rq; ans,ids,path=self.r.relation(s,r); self.last_f=ids; self.last_m=[]
            if not ans:return "I don't know that yet.",False
            if r=='capital_of':return f"The capital of {s.title()} is {ans[0].title()}.",False
            if r=='located_in':return f"{s.title()} is in {ans[0].title()}.",False
            if r=='created_by':return f"{s.title()} was created by {ans[0].title()}.",False
        bq=boolean_query(x) if x.endswith('?') else None
        if bq:
            ok,path,ids=self.r.entails(*bq); self.last_f=ids; self.last_m=[]; s,r,o=bq
            return (f"Yes. {s.title()} is a {o}." if ok else f"I can't prove that {s.title()} is a {o}."),False
        if not x.endswith('?') and self.cfg['agent']['auto_learn_user_statements']:
            tri,facts,_=self.l.learn(x,'conversation',.75); self.last_f=[f['id'] for f in facts]; self.last_m=[]
            return ('Learned: '+'; '.join(f'{s} --{r}--> {o}' for s,r,o in tri)) if tri else 'Stored that as memory.',False
        mem=self.m.search(x,int(self.cfg['memory']['max_retrieval_results']),float(self.cfg['memory']['min_score'])); self.last_m=[m['id'] for m in mem]; self.last_f=[]
        if mem:self.m.touch(self.last_m);return 'I found related memory:\n'+'\n'.join('- '+m['text'] for m in mem[:4]),False
        return "I don't know that yet. Teach me with a statement or /learn.",False
