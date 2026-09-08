from pathlib import Path
import argparse
from .knowledge import KnowledgeStore

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data")
    args = ap.parse_args()

    store = KnowledgeStore(Path(args.root).expanduser().resolve())

    while True:
        print("\nKnowledge manager")
        print("[L]ist  [S]earch  [D]elete  [Q]uit")
        choice = input("Choice: ").strip().lower()[:1]
        if choice == "q":
            break
        if choice == "l":
            items = store.all()
            if not items:
                print("No saved knowledge.")
            for x in items:
                print(f"{x['id']} | {x['query']} -> {x['answer'][:120]}")
        elif choice == "s":
            q = input("Search: ")
            for x in store.search(q, limit=20):
                print(f"{x['id']} | score={x['score']} | {x['query']} -> {x['answer'][:120]}")
        elif choice == "d":
            item_id = input("Knowledge ID to delete: ").strip()
            print("Deleted." if store.delete(item_id) else "Not found.")
