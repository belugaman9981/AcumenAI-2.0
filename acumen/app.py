from __future__ import annotations
from .config import load_config
from .agent import AcumenAgent

BANNER = r"""
    _                                      _    ___   ____  
   / \   ___ _   _ _ __ ___   ___ _ __   / \  |_ _| |___ \ 
  / _ \ / __| | | | '_ ` _ \ / _ \ '_ \ / _ \  | |    __) |
 / ___ \ (__| |_| | | | | | |  __/ | | / ___ \ | |   / __/ 
/_/   \_\___|\__,_|_| |_| |_|\___|_| |_/_/   \_\___| |_____|

AcumenAI 2.0
"""

def run():
    config = load_config()
    agent = AcumenAgent(config)
    print(BANNER)
    print(agent.status())
    print("Type /help for commands.")

    while True:
        try:
            text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAcumen: Shutting down.")
            break

        if not text:
            continue

        response, should_exit = agent.handle(text)
        print(f"\nAcumen: {response}")
        if should_exit:
            break
