from pathlib import Path

def read_text_file(path, max_bytes=2_000_000):
    p = Path(path).expanduser()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(path)
    if p.stat().st_size > max_bytes:
        raise ValueError("File is too large for the simple reader.")
    return p.read_text(encoding="utf-8", errors="ignore")
