import uuid
from .storage import JSONLStore,utc_now
from .text import similarity
class MemoryStore:
    def __init__(self,root): self.store=JSONLStore(root/'memories.jsonl')
    def add(self,text,kind='semantic',source='user',confidence=.75,metadata=None):
        x={'id':str(uuid.uuid4()),'text':text.strip(),'kind':kind,'source':source,'confidence':float(confidence),'created_at':utc_now(),'last_used_at':None,'use_count':0,'metadata':metadata or {}}; self.store.append(x); return x
    def all(self): return self.store.read_all()
    def delete(self,i):
        a=self.all(); b=[x for x in a if x['id']!=i]
        if len(a)==len(b): return False
        self.store.rewrite(b); return True
    def search(self,q,limit=8,min_score=.05):
        out=[]
        for m in self.all():
            s=similarity(q,m['text'])*(0.72+0.28*float(m.get('confidence',.5)))+min(.12,int(m.get('use_count',0))*.01)
            if s>=min_score: out.append(({**m,'score':round(s,4)},s))
        out.sort(key=lambda z:z[1],reverse=True); return [x[0] for x in out[:limit]]
    def touch(self,ids):
        a=self.all(); ch=False
        for m in a:
            if m['id'] in ids: m['use_count']=int(m.get('use_count',0))+1; m['last_used_at']=utc_now(); ch=True
        if ch:self.store.rewrite(a)
