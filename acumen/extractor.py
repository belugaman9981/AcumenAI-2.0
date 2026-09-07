import re
PATTERNS=[
(re.compile(r'^(.+?)\s+is\s+the\s+capital\s+of\s+(.+?)[.!]?$',re.I),'capital_of'),
(re.compile(r'^(.+?)\s+is\s+located\s+in\s+(.+?)[.!]?$',re.I),'located_in'),
(re.compile(r'^(.+?)\s+is\s+in\s+(.+?)[.!]?$',re.I),'located_in'),
(re.compile(r'^(.+?)\s+was\s+(?:created|invented)\s+by\s+(.+?)[.!]?$',re.I),'created_by'),
(re.compile(r'^all\s+(.+?)\s+are\s+(.+?)[.!]?$',re.I),'is_a'),
(re.compile(r'^(.+?)\s+(?:is|are)\s+(?:a|an)\s+(.+?)[.!]?$',re.I),'is_a'),
]
def clean(x): return ' '.join(x.strip(' .?!').lower().split())
def extract(text):
    for rx,r in PATTERNS:
        m=rx.match(text.strip())
        if m:
            s,o=clean(m.group(1)),clean(m.group(2))
            return [(s,r,o)] if s and o and s!=o else []
    return []
