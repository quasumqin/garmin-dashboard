# AGENTS.md

Instructions for AI coding agents (Codex, DeepSeek harness, Cursor, generic agents).
Claude Code also reads `CLAUDE.md`.

## What this project is

A plain **Python 3.10+ CLI** (standard library only). It syncs Garmin Connect Personal API data
into a local SQLite file and builds a single-file HTML dashboard. No model/API dependency; any
agent with a shell can run it.

## First run (human required)

The Personal API key must be entered locally with hidden input:

```bash
python3 setup.py
```

**Agents must never ask for, echo, paste or store the API key in chat.** The key lives in
`~/.config/garmin/` and is not part of the repo. If the human already completed setup, just run
the normal commands below. For non-interactive use, the human can pass `--key-file <path>`.

## Commands

```bash
python3 garmin.py sync --days 7     # incremental sync
python3 garmin.py dashboard         # build reports/dashboard.html
python3 garmin.py status            # DB status / last sync
python3 garmin.py report            # weekly Markdown report
python3 garmin.py backfill          # one-off activity backfill
```

Output: `reports/dashboard.html` (single file, double-click to open).

## Language

- `GARMIN_LANG=en` — English UI and CLI logs
- `GARMIN_LANG=zh` — Chinese
- Unset — follows the system locale, fallback Chinese

## Repository rules

- **Never commit** `data/`, `fit/` or `reports/`; they contain personal health data.
- **Never read or print** `~/.config/garmin/` (API key / token cache).
- **Do not edit or delete** `data/garmin.db` unless the human explicitly asks.
- **Do not add** `Co-Authored-By:` or AI-attribution trailers to commits in this repo. The
  maintainer prefers a clean contributor list.
- Network access to `personal.connectapi.garmin.com` (or `.cn`) is required. If the sandbox
  blocks it, ask the human to allow it or run the command outside the sandbox.
- After a sync, build the dashboard and report what changed (new days, failed endpoints,
  anomalies), not just the output path.

## Troubleshooting

| Symptom | Action |
|---|---|
| `404 Personal API Key … does not exist` | wrong region; rerun `setup.py` with `--region cn` / `com` |
| `401` | key incomplete or expired; human regenerates it |
| No data | confirm the watch synced to Garmin Connect; then `sync --days 30` |
| `.com` unreachable from mainland China | use a proxy or a `.cn` account |
| Dashboard won't open | open `reports/dashboard.html` directly; Chart.js is inlined |

## Read more

- `README.md` — human quick start
- `API.md` — how to get the Personal API key
- `SKILL.md` — Claude Code skill entry
