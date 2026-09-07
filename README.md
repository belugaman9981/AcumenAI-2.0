# AcumenAI 2.0

A new, Pi-first local AI agent architecture built from scratch.

## Goals
- Runs on a Raspberry Pi.
- Keeps persistent data on external/network storage when configured.
- Learns continuously through memory and retrieval, not evolutionary bot training.
- Supports a pluggable local LLM backend later.
- Works today without an API key using a deterministic fallback response engine.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
python main.py
```

## Commands

- `/help`
- `/status`
- `/remember <text>`
- `/forget <memory_id>`
- `/memories [query]`
- `/learn <text>`
- `/ingest <path>`
- `/calc <expression>`
- `/sources`
- `/quit`

## Storage

By default, data is stored in `./data`.

To point persistence at your mounted Windows/NAS path:

```yaml
storage:
  root: /mnt/acumen/data
```

## Architecture

User input → retrieval → planning → tools → response → reflection → learning.

The LLM interface is pluggable. The built-in `RuleBasedBackend` makes the project runnable immediately;
you can later replace it with an Ollama or llama.cpp backend.
