from collections import deque
class Reasoner:
    def __init__(self,g,max_depth=4): self.g=g; self.max_depth=max_depth
    def relation(self,s,r):
        fs=self.g.query(subject=s,relation=r); return ([f['object'] for f in fs],[f['id'] for f in fs],fs)
    def entails(self,s,r,o):
        fs=self.g.query(subject=s,relation=r,obj=o)
        if fs:return True,[fs[0]],[fs[0]['id']]
        if r!='is_a':return False,[],[]
        q=deque([(s,[],0)]); seen={s}
        while q:
            cur,path,d=q.popleft()
            if d>=self.max_depth:continue
            for f in self.g.query(subject=cur,relation='is_a'):
                np=path+[f]
                if f['object']==o:return True,np,[x['id'] for x in np]
                if f['object'] not in seen:seen.add(f['object']);q.append((f['object'],np,d+1))
        return False,[],[]
    def explain(self,path):
        return 'I do not have a proof for that.' if not path else '\n'.join(f"{i}. {f['subject']} --{f['relation']}--> {f['object']}" for i,f in enumerate(path,1))
