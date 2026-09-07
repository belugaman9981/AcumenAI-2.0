from __future__ import annotations
from pathlib import Path
import yaml

DEFAULTS = {
    "app": {"name": "AcumenAI 2.0", "version": "0.1.0"},
    "storage": {"root": "./data"},
    "memory": {"max_retrieval_results": 8, "min_score": 0.05},
    "agent": {
        "auto_learn_user_statements": True,
        "save_conversations": True,
        "reflection_enabled": True,
    },
    "model": {"backend": "rule_based", "model_name": "none"},
}

def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out

def load_config(path: str = "config.yaml") -> dict:
    p = Path(path)
    if not p.exists():
        return DEFAULTS
    with p.open("r", encoding="utf-8") as f:
        user = yaml.safe_load(f) or {}
    return _merge(DEFAULTS, user)
