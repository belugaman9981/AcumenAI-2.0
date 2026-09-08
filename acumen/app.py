from .config import load_config
from .agent import AcumenAgent

def run():
    config = load_config()
    agent = AcumenAgent(config)

    print("AcumenAI 2.0 v0.3.0")
    print("Distributed web verification • symbolic reasoning • no LLM")
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
