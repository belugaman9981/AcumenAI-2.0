from pathlib import Path
import argparse
from .config import load_config
from .client import AcumenClient

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["pi", "local"], default="local")
    ap.add_argument("--root", default=None)
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    cfg = load_config(args.config)
    root = Path(args.root or cfg["storage"]["root"]).expanduser()
    root.mkdir(parents=True, exist_ok=True)

    client = AcumenClient(args.mode, root, cfg)

    print("AcumenAI 2.0 v0.4.0")
    print(f"Mode: {args.mode}")
    if args.mode == "pi":
        print("Pi is answer-only; persistent learning lives on the local computer.")
    else:
        print("Running entirely on this local computer.")
    print("Type /help for commands.")

    try:
        while True:
            text = input("\nYou: ").strip()
            if not text:
                continue
            if text.lower() in {"/quit", "/exit", "quit", "exit"}:
                break
            print("\nAcumen:", client.chat(text))
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        client.close()
