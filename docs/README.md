# AcumenAI browser interface

## Localhost (recommended)

From the project root, install `requirements-local.txt` in a Python virtual
environment and run `python bridge.py` using that environment. Open
**http://localhost:8765**, click **Pair**, and paste the pairing token printed in
the terminal. The bridge serves this folder's interface and the API together;
do not open `index.html` directly or start a separate static server.

Use `python bridge.py --port 8888` for **http://localhost:8888**. The local page
automatically uses its own host and port unless you have saved another bridge URL
in **Pair**. The [main README](../README.md#run-as-a-localhost-website) contains
complete Windows, macOS, and Linux setup commands and troubleshooting.

If no custom pairing token is configured, a new one is generated for each server
run. Pair again after restarting. Save pending learning before stopping the
server with Ctrl+C; closing the tab does not save it automatically.

## Optional GitHub Pages

Publish this `docs/` folder with GitHub Pages.

The page is only a frontend. It does not contain the agent, scraper, or private data.

Run the local bridge on the user's computer:

```bash
python bridge.py --root data --port 8765
```

Add the exact Pages origin (such as `https://your-name.github.io`) to
`web.allowed_origins` in `config.yaml` and restart the bridge. Then use the Pair
button in the page and enter the local pairing token printed in the terminal.
Your browser may require local-network permission or block access from a hosted
HTTPS page to an HTTP bridge. Use the localhost website if that connection fails.

Choose a starter question or type a message. Enter sends and Shift+Enter inserts a
new line. You can copy answers, export the displayed conversation, toggle sources,
or retry a request after fixing a connection problem.

**Find in chat** highlights literal text in your conversation without changing the
draft or exported chat. Use the arrow buttons or Enter / Shift+Enter to move
between matches; Escape closes it.

Expand **New learning** to review answers. Use **Save answer** / **Discard answer**
for one item, or **Save all** / **Discard all** for the whole list. Other pending
items stay available after an individual action. If an item changed in another
tab, refresh the connection before reviewing it again. Expand **Saved knowledge**
to refresh, filter, or delete saved items.
The last 100 messages and recent questions recover after refreshing the same tab,
using browser session storage. Export chat for a lasting copy; closing the tab or
clearing browser storage can remove recovery data. Pairing settings are saved in
the browser. Tabs paired to one bridge share its learning session.

Small conveniences: choose System, Light, or Dark from the theme menu; unsent
drafts recover after a refresh in the same tab. Drafts are kept separately for each
bridge URL. Recent questions lists the last ten distinct questions in this page;
select one to edit it, or press Up in an empty message box to recall the latest.
**Ask again** repeats a question using normal answer and freshness rules while
preserving your current draft. Clearing the chat view also clears recent questions
and this tab's recovery copy.

Use **Check connection** or **Reconnect** to refresh connection and learning state
while keeping your draft. A reload during a request shows an interruption notice
with a manual retry; no question is automatically resent. The server may still
finish that request, so check **New learning** before retrying.

Run the regression suite with `python -B -m pytest -q`. The optional browser test
in `tests/test_browser_usability.py` uses Playwright and an installed Chrome browser.
It starts temporary local servers and uses a separate temporary knowledge store.

Do not commit `data/knowledge.js` or `data/knowledge.json` to a public repository.
