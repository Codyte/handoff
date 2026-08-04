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

## Install the hooks (once per machine)

The skill only *writes* handoffs; the hooks are what *read* them back and watch the context.

```
python load_handoff.py --ensure-hook
```

Registers two hooks in `~/.claude/settings.json`, using this machine's own absolute path:

- `SessionStart` (matcher `startup|clear`) — injects the active handoff at startup and after
  `/clear`; on resume/compact the context already carries the thread, so it stays out.
- `UserPromptSubmit --check-context` — the **context checkpoint**: computes when a handoff starts
  paying for itself and stays silent (zero tokens) until it does. Each further turn re-sends
  `ctx - boot` tokens a fresh session would not, so the switch is worth it once
  `handoff cost / saving per turn` turns of work still remain — typically ~2-3 turns at 200k, ~5 at
  120k on opus. A huge context with the goal one turn away → keep going; that is the point. Context,
  model prices and `boot` (this session's own first turn = what a `/clear` really restarts from) come
  from the transcript; only "how many turns remain" is the agent's estimate. Advisory — it never
  blocks a prompt.

Idempotent: rerunning migrates older installs (adds the matcher, repairs a moved path); no-op if
already correct.

## Usage

The skill drives these, but the script stands alone:

| Command | What it does |
|---------|--------------|
| `load_handoff.py --path` | Print the active handoff file path for the current project |
| `load_handoff.py --archive` | Move the current active handoff into `archive/` before overwriting |
| `load_handoff.py --open` | Show Next steps + Open/blockers of the active handoff (the live TODO) |
| `load_handoff.py --history` | Chronological digest of every archived handoff |
| `load_handoff.py --grep <term>` | `standing.md` (labelled LIVE) + archived handoffs mentioning `<term>`, with date + matching lines |
| `load_handoff.py --context` | Context size, measured boot context, $/turn wasted, and the handoff breakeven in turns |
| `load_handoff.py --spawn` | Open a new Claude Code session here, booted on the handoff (what `/handoff -f` calls). In the VS Code extension it prints the `Ctrl+Shift+P` > *New Conversation* keystroke instead — a console session there would be a different UI |

## Where files live

Automatic, derived from the current directory so the skill and hook always agree:

- **Inside a git repo** → `<repo>/.handoff/active.md`, versioned with the project (commit it so
  handoffs travel with the code).
- **Outside any repo** → `~/.claude/handoff/` (per machine).

Only the single active handoff is auto-loaded at boot. Past handoffs accumulate in `archive/`, read
on demand, never injected — so full history costs zero boot tokens. Prune old archive files freely.

### Two levels

`.handoff/` holds two injected files with opposite lifecycles:

- **`standing.md`** (level 0) — the project's persistent constraints. Edited in place, never
  rewritten by a handoff, never archived, injected even when there is no active handoff. A
  constraint therefore cannot be silently reworded or dropped by a copy-forward. Prune it: every
  line is re-sent on every turn of every future session (cap ~30 lines; `--archive` nudges past it).
- **`active.md`** (level 1) — the session that just ended. Overwritten each handoff, archived first.

Legacy handoffs carrying an inline `## Standing decisions` section are lifted into `standing.md`
automatically on the next `--archive`.

## Documentation

[`SKILL.md`](SKILL.md) — full spec: the handoff format, the archive/navigate commands, and the
boot-hook details.

## License

[MIT](LICENSE)
