# AcumenAI 2.0 — v0.4.5

A lightweight, non-LLM agent that can run in Raspberry Pi answer-node mode or entirely on a local computer.

## Run as a localhost website

The Python bridge now serves **both the website and the API**. You only need one
server; no GitHub Pages setup, Node.js, separate static server, or Pi is required.
Use Python 3.10 or newer. Internet access is needed to install dependencies and
for web research, weather, and location lookups; local calculations work offline.

### Windows PowerShell

Open PowerShell in this project folder and run:

```powershell
py -m venv .local-venv
.\.local-venv\Scripts\python.exe -m pip install -r requirements-local.txt
.\.local-venv\Scripts\python.exe bridge.py
```

These commands do not require activating the environment or changing PowerShell's
execution policy. If `.local-venv` already exists, skip the first command.

### macOS or Linux

From the project folder:

```bash
python3 -m venv .local-venv
.local-venv/bin/python -m pip install -r requirements-local.txt
.local-venv/bin/python bridge.py
```

### Open and pair

1. Keep the terminal running and open **http://localhost:8765** in your browser
   (http://127.0.0.1:8765 also works with the default configuration).
2. Click **Pair**, paste the **Pairing token** printed in the terminal, then click
   **Save and connect**. The bridge URL automatically matches the localhost page,
   including a custom port. Wait for **Connected and paired with local Acumen**.
3. Try `calculate 6*7` or `Solve 2*x + 3 = 11`.
4. Use **New learning → Save all** to keep candidate answers before stopping.
   Stop the server with **Ctrl+C** in the terminal. Closing the browser tab does
   not stop the server or save pending learning automatically.

No `config.yaml` is required. If `web.pairing_token` is missing, empty, or still
`change-me`, the server generates a random token for that run. Pair again after
restarting it. To keep the same token between runs, copy `config.example.yaml` to
`config.yaml` **only if you do not already have one**, then set
`web.pairing_token` to your own long, private random value. Existing custom tokens
continue to work. Pairing settings are remembered by your browser.

For later launches on Windows, run just:

```powershell
.\.local-venv\Scripts\python.exe bridge.py
```

To use another port or knowledge directory:

```powershell
.\.local-venv\Scripts\python.exe bridge.py --port 8888 --root data
```

Then open **http://localhost:8888**. `--config path/to/config.yaml` selects another
configuration file. Without `--root`, the server uses `storage.root` from the
configuration, falling back to `data`. Relative paths are resolved from the
terminal's current directory. Existing saved knowledge is reused.

### Troubleshooting

- **Port already in use:** stop the other Acumen server or choose `--port 8888`.
- **Pairing token not accepted:** copy the token from the current server terminal
  into **Pair**. Generated tokens change whenever the server restarts.
- **Could not reach Acumen:** keep the terminal open, use the URL printed there,
  and check the bridge URL in **Pair**, especially if you previously changed it.
- **Missing Python module:** install `requirements-local.txt` with the same
  environment's Python that you use to run `bridge.py`.

The default server listens only on this computer (`127.0.0.1`). This launcher is
for local use, not public internet hosting. The website serves only its HTML,
JavaScript, and CSS; private data and configuration files are not served as files.
Chat and knowledge APIs still require pairing.

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

## Everyday controls

The browser UI includes starter questions, a multiline composer, a source toggle,
copy buttons, chat export, and retry buttons for failed requests. Enter sends;
Shift+Enter adds a line. You can draft the next question while Acumen works.
The connection indicator checks your pairing token as well as the bridge.

The chat scrolls independently above the composer, which grows as you type.
Replies preserve your reading position when you scroll back; use **Latest message**
to return to the bottom. A waiting indicator appears while Acumen answers. Learning
panels sit beside chat on desktop and below it on smaller screens. Pairing errors
stay in the dialog so you can correct the token, and saved knowledge loads when
you open its panel. Animations respect your system's reduced-motion preference.

Choose a System, Light, or Dark theme. Unsent drafts recover after refreshing the
same tab. The recent-question menu keeps ten distinct questions for quick editing;
Up in an empty message box recalls the last one. **Ask again** repeats a question
without replacing a new draft you are typing.

Open **New learning** to review candidate answers and their sources, then use
**Save all** or **Discard all** without ending the session. **Saved knowledge**
can be filtered by question or answer. **Clear view** clears the visible chat;
saved and pending learning stay available. The transcript is held in tab memory
and can be downloaded as a text file with **Export chat**.

These commands also work in chat and the command line:

| Command | Action |
| --- | --- |
| `/examples` | Show starter questions |
| `/history` | Show the last 30 questions and answers in this session |
| `/again` | Ask the last question again, using normal freshness rules |
| `/sources` | Show sources for the last answer |
| `/knowledge [search words]` | Browse or search saved questions |
| `/learning` | Review pending learning |
| `/save` | Save all pending learning and keep chatting |
| `/discard` | Discard pending learning; keep previously saved knowledge |

In Pi mode, save and discard actions run on the local worker. Browser tabs
connected to the same bridge share its learning session and source preference.

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

## Optional GitHub Pages UI

`docs/` contains the same frontend served by the localhost website. It can also be
published separately through GitHub Pages. For everyday local use, follow
**Run as a localhost website** above.

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

Add your exact Pages origin (for example, `https://your-name.github.io`, without
a repository path) to `web.allowed_origins` in `config.yaml`, restart the bridge,
then use **Pair** on the Pages site with the token printed in the terminal.
Browser local-network permissions or HTTPS-to-HTTP restrictions may block a
hosted page from reaching localhost; the directly served localhost website avoids
that separate-origin setup.

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

## Tests

From the project folder, using the environment created above on Windows:

```powershell
.\.local-venv\Scripts\python.exe -m pip install pytest playwright
.\.local-venv\Scripts\python.exe -B -m pytest -q
```

On macOS/Linux, replace `.\.local-venv\Scripts\python.exe` with
`.local-venv/bin/python`. The browser tests require an installed Google Chrome
browser and otherwise skip. They exercise both the localhost website and the
separately hosted frontend with temporary test data, including pairing, chat,
learning, export, retry, and mobile layout.
