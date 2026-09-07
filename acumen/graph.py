import uuid
from .storage import JSONLStore,utc_now
class KnowledgeGraph:
    def __init__(self,root): self.store=JSONLStore(root/'facts.jsonl')
    def all(self): return self.store.read_all()
    def add(self,s,r,o,source='user',confidence=.85):
        a=self.all()
        for f in a:
            if (f['subject'],f['relation'],f['object'])==(s,r,o):
                f['confidence']=min(1.0,max(float(f.get('confidence',.5)),confidence)); f['updated_at']=utc_now(); self.store.rewrite(a); return f
        f={'id':str(uuid.uuid4()),'subject':s,'relation':r,'object':o,'source':source,'confidence':confidence,'created_at':utc_now(),'updated_at':utc_now(),'use_count':0}; self.store.append(f); return f
    def query(self,subject=None,relation=None,obj=None):
        return [f for f in self.all() if (subject is None or f['subject']==subject) and (relation is None or f['relation']==relation) and (obj is None or f['object']==obj)]
    def touch(self,ids):
        a=self.all(); ch=False
        for f in a:
            if f['id'] in ids: f['use_count']=int(f.get('use_count',0))+1; f['updated_at']=utc_now(); ch=True
        if ch:self.store.rewrite(a)
