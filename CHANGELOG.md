# Changelog

## 0.4.5

- Merged the supplied Codex working-tree edits into the maintained AcumenAI base.
- Added dedicated current-time routing and timezone resolution.
- Prevented stale/fresh data such as time from being reused or permanently learned.
- Tightened automatic knowledge reuse to exact normalized questions.
- Tightened research evidence relevance and causal-answer filtering.
- Preserved the source URLs associated with selected answer evidence.
- Added `tzdata` to local requirements.
- Cleaned the release archive so it contains no `.git`, private `data`, local config, backups, or cache files.
