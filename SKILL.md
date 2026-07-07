---
name: handoff
description: Save a compact handoff of the current session (goal, state, decisions, next steps, key files) so you can /clear and resume cheaply, AND navigate past handoffs. The SessionStart hook auto-loads the active one on the next session. Use when switching tasks, before /clear, when context grows large (over ~150k tokens), when the user says "handoff"/"save state"/"/handoff", OR when the user asks what's still pending/open from before, to see handoff history, or to find something from a past session.
---

# /handoff — save session state so `/clear` is free

Long sessions at large context are the #1 cost driver. `/clear` fixes that but loses the thread —
this skill removes that downside: it writes a terse resume cue that the **SessionStart hook auto-loads**
on the next session, so after `/clear` you continue from exactly where you left off.

## Steps

0. **Ensure the boot hook is installed** (makes the skill self-sufficient on a fresh machine —
   the skill only *writes*; this hook is what *reads* the handoff back at boot):
   ```
   python "$HOME/.claude/skills/handoff/load_handoff.py" --ensure-hook
   ```
   Idempotent: registers the `SessionStart` hook in `~/.claude/settings.json` only if missing,
   using this machine's own absolute path. After the first run on a machine, every later session
   there auto-loads handoffs. No-op if already installed.
1. Get the target path (keeps skill + hook in sync):
   ```
   python "$HOME/.claude/skills/handoff/load_handoff.py" --path
   ```
   (On Windows the same works via Git Bash; or use the printed absolute path directly.)
2. **Archive the outgoing handoff** (chronological history) before overwriting:
   ```
   python "$HOME/.claude/skills/handoff/load_handoff.py" --archive
   ```
   Moves the current active handoff (if non-empty) to `handoff/archive/<project>/<timestamp>.md`.
   The archive is **on-demand only** — the hook never loads it, so boot stays lean.
3. **Write** the active file (path from step 1) with the sections below — terse, high-signal, no
   transcript. Overwrite it (idempotent; one active handoff per project).
4. Tell the user it's saved and they can now `/clear`; the next session resumes automatically.

## Format (keep under ~80 lines — a resume cue, not a log)

```markdown
# Handoff · <project> · <date>

## Goal
<the current objective in 1-2 lines>

## State
- Done: <what's finished>
- In progress: <what's mid-flight, and exactly where>

## Decisions (and why)
- <decision> — <reason>

## Next steps (ordered)
1. <next concrete action>
2. ...

## Key files
- <path:line> — <what's there>

## Open / blockers
- <questions or blockers, if any>
```

## Navigate the history

Three on-demand reads, all derived from existing files (no second index, zero boot cost). After any
of them, verify against live state (git/.env/etc.) — a handoff reflects the moment it was written.

- **What's still pending now** → `load_handoff.py --open` — Next steps + Open/blockers of the
  *active* handoff. The live TODO in one read. Use when the user asks "what's left / still open".
- **What happened over time** → `load_handoff.py --history` — chronological digest (Goal + Next
  steps + Open/blockers) of every archived handoff. Use for prior sessions, recurring blockers.
- **Find a past decision/context** → `load_handoff.py --grep <term>` — archived handoffs mentioning
  `<term>`, with date + matching lines. Use to locate when something appeared without grepping by hand.

(prefix each with `python "$HOME/.claude/skills/handoff/`)

## Notes
- **Where files live:** inside a git repo → `<repo>/.handoff/active.md`, versioned *with the
  project* (commit it so handoffs travel with the code). Outside any repo → `~/.claude/handoff/`
  (per machine). The choice is automatic, derived from the cwd by `handoff_file()`, so skill and
  hook always agree.
- Only the single active handoff is auto-loaded at boot. Past handoffs accumulate in
  `archive/` (`<repo>/.handoff/archive/` in a repo; `~/.claude/handoff/archive/<project>/`
  globally) — one timestamped file each, read on demand, never injected, so full history costs
  zero boot tokens. Prune old archive files freely.
- This does NOT run `/clear` for you (the agent cannot invoke built-in commands). It prepares the
  resume so that when *you* run `/clear`, nothing is lost.
