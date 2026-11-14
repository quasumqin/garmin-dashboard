---
name: garmin-dashboard
description: Sync Garmin Connect Personal API data (activities, sleep, HRV, weight) into local SQLite and build a single-file training & health dashboard; guides first-time users through getting a Personal API key. Use when the user says "sync my Garmin", "build my Garmin dashboard", "analyze my Garmin data", "同步 Garmin", "生成 Garmin 看板" or "分析我的 Garmin 数据".
---

# Garmin Training & Health Dashboard

**English | [中文](SKILL.zh-CN.md)**

This folder is both a standalone Python project and a Claude Code skill. Data stays local.
For non-Claude agents, see `AGENTS.md`; for Claude Code project rules, see `CLAUDE.md`.

## First run

Run the wizard; never ask the user to paste a key into chat:

```bash
python3 setup.py
```

It:

1. asks the region (international `.com` / China `.cn`)
2. opens the Garmin Personal API page so the user can generate and paste the key
   (`getpass`, hidden input)
3. validates the token, syncs 90 days, builds `reports/dashboard.html`

If the user does not know how to get a key, read `API.md` and send the matching link:
- International: <https://connect.garmin.com/app/settings/personalApiToken>
- China: <https://connect.garmin.cn/app/settings/personalApiToken>

**Never** ask for, echo or store an API key in chat. The wizard handles it locally.

## Daily use

```bash
python3 garmin.py sync --days 7     # incremental
python3 garmin.py dashboard         # rebuild
python3 garmin.py status            # DB status
```

Output: `reports/dashboard.html` (single file, double-click to open).

## Language

- Default follows the system locale, fallback Chinese.
- Force English: `GARMIN_LANG=en python3 garmin.py dashboard`
- Force Chinese: `GARMIN_LANG=zh python3 garmin.py dashboard`

## Rules

- Do not commit `data/`, `fit/` or `reports/`; they contain personal health data.
- Do not read or print keys/tokens in `~/.config/garmin/`.
- On 404, check the region first; on 401, ask the user to regenerate the key.
- Mainland China may need a proxy for `.com`; `.cn` accounts use `.cn`.
- Training load is Garmin `activityTrainingLoad` (relative trends only); strength detail only
  includes sets logged on the watch.

## Troubleshooting

| Symptom | Action |
|---|---|
| `404 Personal API Key … does not exist` | wrong region; rerun with `--region cn` / `com` |
| `401` | key incomplete or expired; regenerate |
| No data | confirm the watch synced to Connect; then `sync --days 30` |
| Page won't open | open `reports/dashboard.html` directly; Chart.js is inlined |

See `README.md` and `API.md` for more.
