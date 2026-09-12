# GitHub Pages

Publish this `docs/` folder with GitHub Pages.

The page is only a frontend. It does not contain the agent, scraper, or private data.

Run the local bridge on the user's computer:

```bash
python bridge.py --root data --port 8765
```

Then use the Pair button in the page and enter the local pairing token from `config.yaml`.

Choose a starter question or type a message. Enter sends and Shift+Enter inserts a
new line. You can copy answers, export the displayed conversation, toggle sources,
or retry a request after fixing a connection problem.

Expand **New learning** to review answers and save or discard them without closing
the session. Expand **Saved knowledge** to refresh, filter, or delete saved items.
Chat text stays in tab memory unless you export it; pairing settings are saved in
the browser. Tabs paired to one bridge share its learning session.

Run the regression suite with `python -B -m pytest -q`. The optional browser test
in `tests/test_browser_usability.py` uses Playwright and an installed Chrome browser.
It starts temporary local servers and uses a separate temporary knowledge store.

Do not commit `data/knowledge.js` or `data/knowledge.json` to a public repository.
