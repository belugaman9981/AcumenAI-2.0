import re
def clean(x): return ' '.join(x.strip(' .?!').lower().split())
def relation_query(t):
    for rx,r in [(re.compile(r'^(?:what|which) is the capital of (.+?)\??$',re.I),'capital_of'),(re.compile(r'^where is (.+?)\??$',re.I),'located_in'),(re.compile(r'^who created (.+?)\??$',re.I),'created_by')]:
        m=rx.match(t.strip())
        if m:return clean(m.group(1)),r
    return None
def boolean_query(t):
    m=re.match(r'^(?:is|are)\s+(.+?)\s+(?:a|an)?\s*(.+?)\??$',t.strip(),re.I)
    return (clean(m.group(1)),'is_a',clean(m.group(2))) if m else None
