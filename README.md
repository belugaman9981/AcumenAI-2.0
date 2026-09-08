# AcumenAI 2.0 — v0.3.0

AcumenAI is a lightweight, non-LLM AI agent designed to run on a Raspberry Pi.

v0.3 adds a distributed verification system:

1. The Pi receives a claim.
2. Acumen classifies and extracts the claim.
3. The Pi places a verification job into the shared Acumen data folder.
4. A Windows verifier worker checks the web.
5. The worker writes a structured verification result back into the shared folder.
6. The Pi imports only verified knowledge and answers the user.

No LLM, OpenAI API, Ollama, or llama.cpp is used.

## Architecture

```text
                 WINDOWS PC
        ┌─────────────────────────┐
        │ verifier_worker.py      │
        │                         │
        │ Wikipedia discovery     │
        │ page scraping           │
        │ infobox extraction      │
        │ evidence scoring        │
        └────────────┬────────────┘
                     │
              shared Acumen data
                     │
        verify_queue │ verify_results
                     │
        ┌────────────▼────────────┐
        │ Raspberry Pi            │
        │                         │
        │ cognitive gate          │
        │ claim parser            │
        │ memory/knowledge graph  │
        │ symbolic reasoner       │
        │ response composer       │
        └─────────────────────────┘
```

Because your Windows Acumen folder is already mounted on the Pi as `/mnt/acumen`,
the "transfer" happens through the shared folder. The verifier writes a result on
Windows and the Pi immediately sees it.

## Install on Windows

Open PowerShell:

```powershell
cd "H:\Matthew\Matthew's Python Codes\python\AcumenAI-2.0"
py -m venv .verifier-venv
.\.verifier-venv\Scripts\Activate.ps1
pip install -r requirements.txt
python verifier_worker.py --root data
```

Keep that window open while testing.

## Run on the Pi

```bash
cd /mnt/acumen
source ~/acumen-venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
python main.py
```

On the Pi, `config.yaml` should contain:

```yaml
storage:
  root: /mnt/acumen/data
```

## Example

```text
You: hello
Acumen: Hi. What can I help you with?

You: Ottawa is the capital of Canada.
Acumen: I checked that. Ottawa is the capital of Canada.

You: Ottowa is the capital of USA.
Acumen: That claim does not match the source I checked. The capital of United States is Washington, D.C.
```

## Verification status

Facts have one of these states:

- `verified`
- `rejected`
- `uncertain`

Only `verified` facts are promoted into the trusted knowledge graph.

## Commands

```text
/help
/status
/facts
/memories
/verify <claim>
/why <question>
/calc <expression>
/quit
```
