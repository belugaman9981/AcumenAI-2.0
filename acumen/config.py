from pathlib import Path
import yaml

DEFAULTS = {
    "app": {"name": "AcumenAI 2.0", "version": "0.3.0"},
    "storage": {"root": "/mnt/acumen/data"},
    "verification": {
        "enabled": True,
        "wait_seconds": 15,
        "poll_interval": 0.25,
        "minimum_confidence": 0.75,
    },
    "memory": {"max_retrieval_results": 8, "min_score": 0.05},
    "reasoning": {"max_depth": 4},
}

def deep_merge(base, override):
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def load_config(path="config.yaml"):
    p = Path(path)
    if not p.exists():
        return DEFAULTS
    with p.open("r", encoding="utf-8") as f:
        return deep_merge(DEFAULTS, yaml.safe_load(f) or {})
