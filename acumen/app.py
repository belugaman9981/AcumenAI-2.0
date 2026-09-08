from .config import load_config
from .agent import Agent
def run():
    a=Agent(load_config()); print('AcumenAI 2.0 v0.2.1 — symbolic cognition, no LLM'); print(a.status()); print('Type /help for commands.')
    while True:
        try:t=input('\nYou: ').strip()
        except (EOFError,KeyboardInterrupt):print('\nAcumen: Shutting down.');break
        if not t:continue
        r,q=a.handle(t); print('\nAcumen:',r)
        if q:break
