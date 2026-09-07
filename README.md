# AcumenAI 2.0 — v0.2

A lightweight, Pi-first AI agent built **without an LLM**.

Core pipeline:
`input -> parse -> classify -> retrieve -> reason -> act -> compose -> learn`

Features:
- symbolic parsing and intent detection
- semantic + episodic memory
- persistent knowledge graph
- rule-based inference
- pattern/reinforcement learning
- calculator and file tools
- no API keys, OpenAI, Ollama, or llama.cpp

## Pi start
```bash
cd /mnt/acumen
source ~/acumen-venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
python main.py
```

Recommended storage:
```yaml
storage:
  root: /mnt/acumen/data
```

## Commands
`/help`, `/status`, `/remember`, `/forget`, `/memories`, `/learn`, `/ingest`, `/facts`, `/why`, `/calc`, `/feedback good`, `/sources`, `/quit`

## Example
Teach:
```text
Ottawa is the capital of Canada.
Whales are a mammals.
All mammals are warm-blooded.
```
Ask:
```text
What is the capital of Canada?
Are whales warm-blooded?
/why Are whales warm-blooded?
```
