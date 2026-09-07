from pathlib import Path
import json, threading
from datetime import datetime, timezone
def utc_now(): return datetime.now(timezone.utc).isoformat()
class JSONLStore:
    def __init__(self,path:Path):
        self.path=path; self.path.parent.mkdir(parents=True,exist_ok=True); self.lock=threading.RLock()
        if not self.path.exists(): self.path.touch()
    def append(self,item):
        with self.lock,self.path.open('a',encoding='utf-8') as f: f.write(json.dumps(item,ensure_ascii=False)+'\n')
    def read_all(self):
        out=[]
        if not self.path.exists(): return out
        with self.lock,self.path.open('r',encoding='utf-8') as f:
            for line in f:
                try: out.append(json.loads(line))
                except: pass
        return out
    def rewrite(self,items):
        tmp=self.path.with_suffix(self.path.suffix+'.tmp')
        with self.lock,tmp.open('w',encoding='utf-8') as f:
            for x in items: f.write(json.dumps(x,ensure_ascii=False)+'\n')
        tmp.replace(self.path)
