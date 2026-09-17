from pathlib import Path
from copy import deepcopy
import math
import yaml

DEFAULTS = {
    "app": {"name": "AcumenAI 2.0", "version": "0.4.0"},
    "storage": {"root": "data"},
    "research": {
        "max_search_results": 5,
        "max_pages_to_scrape": 3,
        "request_timeout": 10,
        "max_page_chars": 120000,
        "max_workers": 4,
        "cache_ttl_seconds": 300,
        "cache_max_entries": 128,
        "max_page_bytes": 524288,
    },
    "tasks": {"wait_seconds": 45, "poll_interval": 0.25},
    "learning": {"recheck_after_days": 30},
    "web": {
        "bridge_host": "127.0.0.1",
        "bridge_port": 8765,
        "allowed_origins": ["http://127.0.0.1:8765", "http://localhost:8765"],
        "pairing_token": "change-me",
    },
}


def normalize_recheck_after_days(value):
    """Use a positive, finite lifetime, falling back safely for invalid settings."""
    try:
        days = float(value) if not isinstance(value, bool) else 0
    except (TypeError, ValueError, OverflowError):
        return 30
    return days if math.isfinite(days) and days > 0 else 30


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
    config = deepcopy(DEFAULTS)
    if p.exists():
        config = _merge(config, yaml.safe_load(p.read_text(encoding="utf-8")) or {})
    learning = config.get("learning")
    if not isinstance(learning, dict):
        learning = {}
    config["learning"] = {
        **learning,
        "recheck_after_days": normalize_recheck_after_days(learning.get("recheck_after_days", 30)),
    }
    return config
