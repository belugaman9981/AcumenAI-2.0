import argparse
import os
from pathlib import Path
import shutil
import sys

from .config import load_config
from .client import AcumenClient
from . import __version__


def build_parser():
    parser = argparse.ArgumentParser(
        description="Ask questions, research topics, and save useful answers locally.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py\n"
            "  python main.py --ask \"solve 2*x + 3 = 11\"\n"
            "  python main.py --mode pi --root /mnt/acumen/data"
        ),
    )
    parser.add_argument("--mode", choices=["pi", "local"], default="local",
                        help="Run locally or send tasks to a local worker from a Pi.")
    parser.add_argument("--root", metavar="DIRECTORY", default=None,
                        help="Directory for knowledge, sessions, and queued tasks.")
    parser.add_argument("--config", metavar="FILE", default="config.yaml",
                        help="Configuration file to load (default: config.yaml).")
    parser.add_argument("--ask", metavar="QUESTION",
                        help="Answer one question, then exit instead of opening the prompt.")
    parser.add_argument("--output", metavar="FILE",
                        help="Write a one-shot answer to a UTF-8 file.")
    parser.add_argument("--no-sources", action="store_true",
                        help="Hide source links in answers for this session.")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto",
                        help="Use terminal color automatically, always, or never (default: auto).")
    parser.add_argument("--version", action="version", version=f"AcumenAI 2.0 v{__version__}")
    return parser


def use_color(setting):
    if setting == "always":
        return True
    if setting == "never":
        return False
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def styled(text, code, color):
    return f"\033[{code}m{text}\033[0m" if color else text


def terminal_width():
    return max(48, min(shutil.get_terminal_size(fallback=(80, 24)).columns, 96))


def divider(color, character="-"):
    return styled(character * terminal_width(), "2;36", color)


def clear_terminal():
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")


def print_answer(answer, color):
    print()
    print(divider(color))
    print(styled("ACUMEN", "1;36", color))
    print(divider(color))
    print(answer)


def print_welcome(mode, root, color):
    print()
    print(divider(color, "="))
    print(styled("ACUMENAI 2.0", "1;36", color))
    print(styled(f"v{__version__} | {mode.upper()} MODE", "2", color))
    print(f"Storage: {root}")
    print(divider(color, "="))
    print()
    if mode == "pi":
        print("Answers run through the local worker; learning stays on that computer.")
    else:
        print("Answers and learning stay on this computer.")
    print()
    print(styled("QUICK COMMANDS", "1;36", color))
    print("/examples for ideas  |  /learning to review answers  |  /status for session details")
    print("/help for all commands  |  /clear to redraw  |  /quit to exit")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.output and not args.ask:
        parser.error("--output requires --ask.")
    color = use_color(args.color)

    cfg = load_config(args.config)
    root = Path(args.root or cfg["storage"]["root"]).expanduser()
    root.mkdir(parents=True, exist_ok=True)

    client = AcumenClient(args.mode, root, cfg)
    if args.no_sources:
        client.show_sources = False

    try:
        if args.ask:
            answer = client.chat(args.ask)
            if args.output:
                output = Path(args.output).expanduser()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(f"{answer.rstrip()}\n", encoding="utf-8")
            print_answer(answer, color)
            return

        print_welcome(args.mode, root, color)
        while True:
            text = input(f"\n{styled('You', '1;33', color)} > ").strip()
            if not text:
                continue
            if text.lower() in {"/clear", "clear"}:
                clear_terminal()
                print_welcome(args.mode, root, color)
                continue
            if text.lower() in {"/quit", "/exit", "quit", "exit"}:
                print(styled("Session ended.", "2", color))
                break
            print_answer(client.chat(text), color)
    except (KeyboardInterrupt, EOFError):
        print(styled("\nSession ended.", "2", color))
    finally:
        client.close()
