# Migration to v0.2.2

Keep your existing `data/` directory.

For a clean upgrade:
1. Back up `/mnt/acumen/data`.
2. Replace the code files/folders with this release.
3. Keep `data/`.
4. Run `python main.py`.

This build restores the files that were missing in the prior package:
- `acumen/conversations.py`
- `acumen/knowledge.py`
- `acumen/tools/base.py`
- `acumen/tools/files.py`
