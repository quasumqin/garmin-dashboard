# CLAUDE.md

Shared agent rules live in [AGENTS.md](AGENTS.md). This file only adds Claude Code specifics.

## Entry points

- If this folder is installed at `~/.claude/skills/garmin-dashboard/`, `SKILL.md` is the skill
  entry point.
- If the repository is opened directly, follow `AGENTS.md` and `README.md`.

## Rules

- Never ask for or echo the Garmin Personal API key in chat. The human runs `python3 setup.py`
  once; the key is hidden input and stays in `~/.config/garmin/`.
- After setup: `python3 garmin.py sync --days 7` then `python3 garmin.py dashboard`.
- Never commit `data/`, `fit/` or `reports/`.
- Do not add `Co-Authored-By: Claude …` or similar AI-attribution trailers to commits in this
  repository. The maintainer wants a clean contributor list.
- Language: `GARMIN_LANG=en` for English UI/CLI, `GARMIN_LANG=zh` for Chinese; unset follows the
  system locale with a Chinese fallback.

## Output

`reports/dashboard.html` — single-file, offline, no upload. Report what changed after a sync,
not only the path.
