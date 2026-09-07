import re, math
from collections import Counter
STOP={"a","an","the","is","are","was","were","of","to","in","on","at","for","from","with","and","or","what","who","where","when","why","how","does","do","did","can","this","that"}
def tokens(t): return [x.lower() for x in re.findall(r"[A-Za-z0-9_'-]+",t) if x.lower() not in STOP]
def similarity(a,b):
    A,B=Counter(tokens(a)),Counter(tokens(b))
    if not A or not B:return 0.0
    d=sum(v*B.get(k,0) for k,v in A.items()); na=math.sqrt(sum(v*v for v in A.values())); nb=math.sqrt(sum(v*v for v in B.values()))
    return d/(na*nb) if na and nb else 0.0
