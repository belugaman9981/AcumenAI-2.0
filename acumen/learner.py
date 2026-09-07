from .extractor import extract
class Learner:
    def __init__(self,m,g): self.m=m; self.g=g
    def learn(self,text,source='user',confidence=.85):
        triples=extract(text); facts=[self.g.add(s,r,o,source,confidence) for s,r,o in triples]
        mem=self.m.add(text,'semantic' if triples else 'episodic',source,confidence if triples else .55,{'fact_ids':[f['id'] for f in facts]})
        return triples,facts,mem
    def reinforce(self,mids,fids): self.m.touch(mids); self.g.touch(fids)
