from pathlib import Path
import yaml

DEFAULTS = {
    "app": {"name": "AcumenAI 2.0", "version": "0.4.0"},
    "storage": {"root": "data"},
    "research": {
        "max_search_results": 5,
        "max_pages_to_scrape": 3,
        "request_timeout": 10,
        "max_page_chars": 120000,
    },
    "tasks": {"wait_seconds": 45, "poll_interval": 0.25},
    "web": {
        "bridge_host": "127.0.0.1",
        "bridge_port": 8765,
        "allowed_origins": ["http://127.0.0.1:8765", "http://localhost:8765"],
        "pairing_token": "change-me",
    },
}

def _merge(a, b):
    out = dict(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out

def load_config(path="config.yaml"):
    p = Path(path)
    if not p.exists():
        return DEFAULTS
    return _merge(DEFAULTS, yaml.safe_load(p.read_text(encoding="utf-8")) or {})
