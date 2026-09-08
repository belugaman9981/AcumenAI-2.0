
## v0.4.3 live weather fix

Weather is no longer treated as a generic web-research question.

Requests such as:

```text
what is the weather in Vancouver BC
weather in Toronto
temperature in Seattle
forecast for London
```

are routed to a dedicated live weather provider on the local computer. The Pi still
only receives and displays the answer.

Weather is deliberately **not** stored as learned permanent knowledge because it becomes stale.

v0.4.3 also fixes the startup banner so it reads the package version instead of using
a hard-coded old version string.


# AcumenAI 2.0 — v0.4.3

A lightweight, non-LLM agent that can run in two modes:

- **Pi mode**: the Raspberry Pi is only the chat/answer node. Web work and all persistent storage live on your local computer.
- **Local mode**: no Pi is required. The same agent, worker, storage, and web tools run directly on your computer.

The core is not a wrapper around an LLM.

## What v0.4 changes

Acumen no longer needs one hard-coded rule for every task.

It has a generic task router:

```text
user request
   ↓
intent router
   ├─ greeting
   ├─ calculator/math
   ├─ homework
   ├─ web research
   ├─ factual verification
   └─ stored-knowledge query
   ↓
local worker / local executor
   ↓
search + scrape + rank evidence
   ↓
structured answer
   ↓
Pi or local CLI displays answer
```

Examples:

```text
find me flights from YVR to PEK
research why the sky is blue
who invented Python?
help me with my homework: solve 2*x + 3 = 11
find the latest information about Raspberry Pi 5
```

For arbitrary web questions, Acumen searches the web, opens a few result pages,
extracts relevant sentences, and returns an evidence-based answer without an LLM.



## v0.4.3 research fix

The research engine now uses multiple retrieval paths instead of depending on one
DuckDuckGo HTML page:

- DuckDuckGo Instant Answer API
- Wikipedia's MediaWiki API
- DuckDuckGo HTML search as an additional source

It also detects question type (`why`, `who`, `where`, `when`, `how`) and ranks
sentences accordingly. A question such as `why is the sky blue?` now prioritizes
causal/explanatory sentences instead of merely returning a source list.

## Source display mode

Sources are shown by default.

Hide them for the current Acumen session:

```text
/hide-source
```

Show them again:

```text
/show-source
```

Aliases `/hide-sources` and `/show-sources` also work.

This only changes what Acumen prints. Source metadata is still retained with research results and candidate knowledge so it can be reviewed before saving.

## Temporary learning and save-on-exit

During a session, useful results become **candidate learnings** on the local computer.

They are *not* permanent yet.

When a local session ends:

```text
Acumen learned 4 candidate items this session.
[S]ave all  [R]eview one-by-one  [D]iscard
```

In Pi mode, the Pi sends a `finalize_session` task. The Windows worker then shows
that prompt on the Windows computer.

Permanent knowledge is stored locally in:

```text
data/knowledge.json
```

A browser-friendly export is generated at:

```text
data/knowledge.js
```

`knowledge.json` is the canonical file. `knowledge.js` is only an export.

You can delete stored information at any time:

```bash
python manage_knowledge.py --root data
```

Do not commit your private `data/` folder to GitHub.

## Pi mode

The Pi should use your existing network-mounted project:

```text
/mnt/acumen
```

Pi:

```bash
cd /mnt/acumen
source ~/acumen-venv/bin/activate
pip install -r requirements-pi.txt
python main.py --mode pi --root /mnt/acumen/data
```

Windows worker:

```powershell
cd "H:\Matthew\Matthew's Python Codes\python\AcumenAI-2.0"
py -m venv .worker-venv
.\.worker-venv\Scripts\Activate.ps1
pip install -r requirements-local.txt
python worker.py --root data
```

The Pi stores no permanent knowledge locally. Queue files and knowledge live on
the Windows-backed share.

## Local mode — no Pi

Windows:

```powershell
cd "H:\Matthew\Matthew's Python Codes\python\AcumenAI-2.0"
py -m venv .local-venv
.\.local-venv\Scripts\Activate.ps1
pip install -r requirements-local.txt
python main.py --mode local --root data
```

Local mode executes web tasks directly and asks whether to save learning when you exit.

## GitHub Pages UI

`docs/` contains a static frontend suitable for GitHub Pages.

Important limitation: **GitHub Pages is static hosting. It cannot run Acumen's Python
worker, scrape websites, or safely store private user data.**

The Pages UI connects to a bridge running on the user's own computer:

```powershell
python bridge.py --root data --port 8765
```

Then the static page talks to:

```text
http://127.0.0.1:8765
```

The bridge uses a local pairing token. This is pairing, not full GitHub OAuth.

A real "Sign in with GitHub" system requires an OAuth backend or device-flow
implementation; a static GitHub Pages site alone should not contain OAuth secrets.

## Homework

Acumen uses two paths:

- symbolic math/equations -> SymPy on the local computer
- general homework/research -> web search + page scraping + evidence ranking

Because there is no LLM, free-form synthesis is intentionally extractive rather than
pretending to generate knowledge it does not have.

## Privacy design

- Pi: no permanent knowledge
- Local PC: all permanent knowledge
- GitHub repo: code only
- GitHub Pages: UI only
- `data/`: ignored by Git
