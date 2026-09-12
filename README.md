# AcumenAI 2.0 — v0.4.5

A lightweight, non-LLM agent that can run in Raspberry Pi answer-node mode or entirely on a local computer.

## v0.4.5 — Codex edits merged

This build uses the Codex-edited v0.4.4 working tree as the new base. It keeps the weather, research, source-display, session-learning, and local/Pi modes, and adds the newer relevance/time fixes.

Changes carried forward from the Codex edits:

- dedicated current-time intent and timezone service
- current-time results are always fresh and are never permanently learned
- exact-question knowledge reuse instead of loose word-overlap reuse
- stricter research relevance scoring
- sources/evidence are retained for the sentences actually used
- `tzdata` added for reliable Windows timezone support

This release package intentionally excludes `.git/`, `config.yaml`, `data/`, backups, virtual environments, and Python caches. Keep your existing local `data/` directory when upgrading.

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



## v0.4.x research fix

The research engine now uses multiple retrieval paths instead of depending on one
DuckDuckGo HTML page:

- DuckDuckGo Instant Answer API
- Wikipedia's MediaWiki API
- DuckDuckGo HTML search as an additional source

It also detects question type (`why`, `who`, `where`, `when`, `how`) and ranks
sentences accordingly. A question such as `why is the sky blue?` now prioritizes
causal/explanatory sentences instead of merely returning a source list.

## Current time and answer relevance

Clock questions use a dedicated timezone lookup:

```text
what is the time in shenzhen right now?
what time is it in Vancouver BC?
current time in New York
```

Acumen resolves the location using Open-Meteo, then converts the worker computer's
current UTC clock using IANA timezone rules, including daylight-saving changes.
Only the location mapping is cached; every answer reads the clock again. Current
time answers bypass saved knowledge and are never saved as permanent learning.
Unresolved locations produce a clear failure instead of unrelated web articles.

Install the updated `requirements-local.txt` on the worker (including `tzdata`
for Windows), and keep its system clock synchronized.

Automatic knowledge reuse now requires the same question, rather than accepting
a different question that shares common words. Research rejects weak topic matches
and retains source links for the sentences it actually uses.

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

## Faster fetching and cleaner learning

Research fetches independent search providers and pages concurrently, with a small
worker limit. Wikipedia summaries are retrieved in a batch. Recently fetched
results and pages can be reused from a bounded, temporary cache.

Page downloads have a size limit, and extraction focuses on readable article
content. Duplicate sources and sentences are filtered before building an answer.
Research results retain the source for each selected sentence, and that evidence
travels with candidate learnings into saved knowledge.

Repeated learnings merge their source links instead of creating duplicate entries.
Saving all items, or the items selected during review, writes knowledge in one
batch. Learning still uses the existing save, review, or discard flow.

Fetch limits and cache settings are available under `research` in
`config.example.yaml`. Set `cache_ttl_seconds: 0` to disable caching, or reduce
`max_workers` for a slower connection.

## Temporary learning and save-on-exit

### Learning and processing improvements

Stable questions can reuse a supported answer from the current session before it
is saved. Saved and pending answers are checked together: when versions differ,
Acumen researches again instead of choosing whichever was saved last. This is a
conservative text comparison, not a semantic contradiction detector; differently
worded answers can also trigger research. Use `/knowledge` and `/delete <id>` to
review and remove outdated saved versions.

Question matching understands contractions (including curly apostrophes) while
preserving names, numbers, negation, word order, and symbols such as `C++`.
Explicit search requests still fetch again. Short topics, explanation requests,
and yes/no questions are routed to research, and repeated answers record usage
without increasing their confidence.

Automatic learning requires a successful answer, a source URL, and a confidence
score of at least 0.6. These scores are heuristics, not calibrated probabilities.
Snippet-only answers can be displayed but do not become learning candidates;
each selected passage needs page support. Matching passages from multiple sources
retain their provenance without repeating the sentence in the answer. Live-data
queries use the same freshness rules for retrieval, caching, and learning.

The save, review, or discard choice below still controls permanent learning.

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
