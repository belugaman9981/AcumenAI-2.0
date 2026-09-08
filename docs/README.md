# GitHub Pages

Publish this `docs/` folder with GitHub Pages.

The page is only a frontend. It does not contain the agent, scraper, or private data.

Run the local bridge on the user's computer:

```bash
python bridge.py --root data --port 8765
```

Then use the Pair button in the page and enter the local pairing token from `config.yaml`.

Do not commit `data/knowledge.js` or `data/knowledge.json` to a public repository.
