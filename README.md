# handoff

Save a compact, high-signal handoff of your current session — goal, state, decisions, next steps,
key files — so you can `/clear` and resume cheaply instead of dragging a huge context forward. A
`SessionStart` hook auto-loads the active handoff on your next session, so after `/clear` you
continue from exactly where you left off.

A dependency-free Python script + [Claude Code](https://claude.com/claude-code) skill (`SKILL.md`).

## Why

Long sessions at large context are the #1 cost driver. `/clear` fixes that but loses the thread.
This removes the downside: it writes a terse resume cue that the boot hook reads back automatically,
so clearing is free.

## Requirements

Python 3 (standard library only — no `pip install`).

## Install the boot hook (once per machine)

The skill only *writes* handoffs; this hook is what *reads* them back at the start of each session.

```
python load_handoff.py --ensure-hook
```

Idempotent: registers the `SessionStart` hook in `~/.claude/settings.json` only if missing, using
this machine's own absolute path. No-op if already installed.

## Usage

The skill drives these, but the script stands alone:

| Command | What it does |
|---------|--------------|
| `load_handoff.py --path` | Print the active handoff file path for the current project |
| `load_handoff.py --archive` | Move the current active handoff into `archive/` before overwriting |
| `load_handoff.py --open` | Show Next steps + Open/blockers of the active handoff (the live TODO) |
| `load_handoff.py --history` | Chronological digest of every archived handoff |
| `load_handoff.py --grep <term>` | Archived handoffs mentioning `<term>`, with date + matching lines |

## Where files live

Automatic, derived from the current directory so the skill and hook always agree:

- **Inside a git repo** → `<repo>/.handoff/active.md`, versioned with the project (commit it so
  handoffs travel with the code).
- **Outside any repo** → `~/.claude/handoff/` (per machine).

Only the single active handoff is auto-loaded at boot. Past handoffs accumulate in `archive/`, read
on demand, never injected — so full history costs zero boot tokens. Prune old archive files freely.

## Documentation

[`SKILL.md`](SKILL.md) — full spec: the handoff format, the archive/navigate commands, and the
boot-hook details.

## License

[MIT](LICENSE)
