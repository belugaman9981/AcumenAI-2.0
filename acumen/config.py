from pathlib import Path
import yaml
DEFAULTS={"app":{"name":"AcumenAI 2.0","version":"0.2.0"},"storage":{"root":"/mnt/acumen/data"},"memory":{"max_retrieval_results":8,"min_score":0.05},"reasoning":{"max_depth":4},"agent":{"auto_learn_user_statements":True,"save_conversations":True}}
def merge(a,b):
    o=dict(a)
    for k,v in (b or {}).items():
        o[k]=merge(o[k],v) if isinstance(v,dict) and isinstance(o.get(k),dict) else v
    return o
def load_config(path='config.yaml'):
    p=Path(path)
    if not p.exists(): return DEFAULTS
    with p.open('r',encoding='utf-8') as f: return merge(DEFAULTS,yaml.safe_load(f) or {})
