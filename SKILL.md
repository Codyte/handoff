---
name: handoff
description: Save a compact handoff of the current session (goal, state, decisions, next steps, key files) so you can /clear and resume cheaply, AND navigate past handoffs. The SessionStart hook auto-loads the active one on the next session. Use when switching tasks, before /clear, when context grows large (over ~150k tokens), when the user says "handoff"/"save state"/"/handoff", OR when the user asks what's still pending/open from before, to see handoff history, or to find something from a past session. Also writes a split handoff (router + one track file per agent) when the work is to continue on two agents running in parallel.
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
   using this machine's own absolute path. The hook fires only on `startup|clear` — on
   resume/compact the context already carries the thread, so injecting there would waste tokens.
   Older installs without the matcher are migrated in place. No-op if already correct.
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
   transcript. Overwrite it (idempotent; one active handoff per project). Splitting the work
   across two agents that run at the same time → see **Split mode** below.
4. Tell the user it's saved and they can now `/clear`; the next session resumes automatically.

## Format (keep under ~80 lines — a resume cue, not a log)

```markdown
# Handoff · <project> · <date>

## Goal
<the current objective in 1-2 lines>

## State
- HEAD: <`git rev-parse --short HEAD` at write time — on resume, compare against the current one
  to detect drift; omit outside a repo>
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

## Split mode — two agents at once (optional)

When the remaining work has a part that **monopolizes one resource** and a part that doesn't, you
can hand off to two agents running side by side. The user starts each one with "continue 1" /
"continue 2". Same `.handoff/` folder, one extra file per track:

- `active.md` becomes a **router + shared state** — it is the only file auto-loaded at boot, so it
  must stay small. It says which track file to read, carries the state both agents need (HEAD,
  environment, decisions already taken, hard rules), and nothing else.
- `track1.md`, `track2.md` — one per agent, same sections as the normal format (so `--open` still
  parses them) plus a **Territory** section: files it writes, files it must not touch.
- `--archive` folds the track files into the one archived handoff and removes them, so a later
  single-track handoff can't strand a track nobody routes to.

**Split by the exclusive resource, not by "half the tasks each".** The split is only safe when
exactly one track can touch the contended thing — a single-session API or device, a dev server on
a fixed port, a test database, a build output, a migration. Everything else goes to the other track.

Three rules make it hold; write them into `active.md` explicitly, in the terms of that project:
1. **One owner per exclusive resource** — name it, and say the other track never calls it, not even
   read-only.
2. **No shared rebuild** — nobody regenerates an artifact the other is using (binary, container,
   schema, generated client). Give the non-owner work that doesn't need a build.
3. **No `git add -A`** — same working tree means `-A` sweeps in the other agent's half-finished
   work. Both commit with explicit paths.

Then list, per track, which files it owns. For a file both must edit (a plan, a changelog), name
the section each owns and require a re-read immediately before the edit.

**Don't split when**: the parts are sequential (2 needs 1's output), both need the exclusive
resource, or either half is under ~a session of work — the coordination costs more than it buys.
Skip it and write one handoff.

## Navigate the history

Three on-demand reads, all derived from existing files (no second index, zero boot cost). After any
of them, verify against live state (git/.env/etc.) — a handoff reflects the moment it was written.

- **What's still pending now** → `load_handoff.py --open` — Next steps + Open/blockers of the
  *active* handoff, plus each track file's, labelled, when the handoff is split. The live TODO in
  one read. Use when the user asks "what's left / still open".
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
- **New machine / portability:** the handoff *files* travel with the repo — `<repo>/.handoff/`
  (active + `archive/`) is versioned, so a clone carries the full state. What does **not** travel is
  the auto-load **hook**: it lives in that machine's `~/.claude/settings.json`. So on a fresh machine
  run step 0 (`--ensure-hook`) **once** — from then on every repo with a `.handoff/` auto-resumes.
  That first run is the only setup; before it, a clone's handoff is still readable by hand
  (`--open` / just open `.handoff/active.md`), it just isn't injected at boot yet.
  (A committed *per-project* hook was considered and rejected: Claude Code prompts you to trust a
  cloned repo's hooks anyway, so it would not save that one-time setup — it would only move it from
  one command to one trust prompt, per clone instead of per machine — while adding a reader script
  and a double-injection guard to every repo. Net loss.)
- Handoffs are committed with the repo — never put secrets in them (tokens, passwords, `.env`
  values); reference the file that holds them instead.
- This does NOT run `/clear` for you (the agent cannot invoke built-in commands). It prepares the
  resume so that when *you* run `/clear`, nothing is lost.
