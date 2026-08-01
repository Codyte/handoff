---
name: handoff
description: Save a compact handoff of the current session (goal, state, decisions, next steps, key files) so you can /clear and resume cheaply, AND navigate past handoffs. The SessionStart hook auto-loads the active one on the next session. Use when switching tasks, before /clear, when context grows large (over ~150k tokens), when the user says "handoff"/"save state"/"/handoff", OR when the user asks what's still pending/open from before, to see handoff history, or to find something from a past session. Also writes a split handoff (router + one track file per agent) when the work is to continue on two agents running in parallel.
---

# /handoff — save session state so `/clear` is free

Long sessions at large context are the #1 cost driver. `/clear` fixes that but loses the thread —
this skill removes that downside: it writes a terse resume cue that the **SessionStart hook auto-loads**
on the next session, so after `/clear` you continue from exactly where you left off.

## Steps

0. **Ensure the hooks are installed** (makes the skill self-sufficient on a fresh machine —
   the skill only *writes*; the hooks are what *read* the handoff back and watch the context):
   ```
   python "$HOME/.claude/skills/handoff/load_handoff.py" --ensure-hook
   ```
   Idempotent: registers both hooks in `~/.claude/settings.json` only if missing, using this
   machine's own absolute path. `SessionStart` (matcher `startup|clear`) injects the handoff at
   boot — on resume/compact the context already carries the thread, so injecting there would waste
   tokens. `UserPromptSubmit --check-context` is the context checkpoint below. Older installs are
   migrated in place. No-op if already correct.
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
   With **`/handoff -f`** (fast handoff), also run
   ```
   python "$HOME/.claude/skills/handoff/load_handoff.py" --spawn
   ```
   after writing the file: it opens a new Claude Code session in this same directory, which boots
   with the handoff via the `SessionStart` hook. Then tell the user to `/clear` or close this one —
   a skill cannot invoke the harness's own commands, so ending the old session stays manual; `-f`
   only removes the "start the next one and wait for it to load" half. Skip `-f` when the work is
   not actually continuing right now (nothing to resume into).
   **In the VS Code extension** (`CLAUDE_CODE_ENTRYPOINT=claude-vscode`) a spawned console would be
   a different UI, and VS Code cannot fire an extension command from outside — so `--spawn` prints
   the keystroke instead (`Ctrl+Shift+P` > *Claude Code: New Conversation*). Relay it as-is.
5. **Close with an effort recommendation** for step 1 of *Next steps* — see below. Name the model
   actually in use (the resume session inherits it), so the user can dial it before continuing.

## Format (keep under ~80 lines — a resume cue, not a log)

```markdown
# Handoff · <project> · <date>

## Goal
<the current objective in 1-2 lines>

## State
- HEAD: <`git rev-parse --short HEAD` at write time — on resume, compare against the current one
  to detect drift; omit outside a repo>
- Live state: <anything the resume inherits but cannot see: which app/file/project is open, what is
  running or deployed, a device or account left in a non-default mode, data already written.
  Skip the line when there is none — but check first; this is the state no diff records>
- Done: <what's finished>
- In progress: <what's mid-flight, and exactly where>

## Decisions (and why)
- <decision> — <reason>
- <what was tried and rejected — with the reason it failed. Without this the resume re-walks dead
  ends at full price; a rejected path is worth as much as a chosen one>

## Next steps (ordered)
1. <next concrete action>
2. ...

## Key files
- <path:line — or URL, doc, ticket, dataset, sheet: whatever the work actually lives in> — <what's there>
- <the `__navi__.md` of each folder the next steps touch — one read orients the resuming session
  instead of a blind grep sweep; regenerate it first if this session moved symbols around>

## Open / blockers
- <questions or blockers, if any>

## Skills
- <skill name to auto-inject next session — omit the whole section to keep the machine defaults>
- -<name> <— a leading dash removes a default instead of adding one>

## Effort
<low|medium|high> for step 1 — <reason>. Raise if <trigger>.
```

## Context checkpoint (automatic)

Cost per turn is the whole context re-sent, so a long session gets expensive well before it hits any
limit. But a big context is **not** by itself a reason to hand off: what decides is how much work is
left. The right question is a breakeven, not a threshold.

```
saving per turn = (ctx - boot) x cache-read price      # what a fresh session would not re-send
one-off cost    = ctx x cache-read                     # the handoff turn reads the full context
                + handoff output + what the fresh session re-reads to get back on the thread
breakeven       = one-off cost / saving per turn       # in turns of work still remaining
```

Growth per turn happens on both sides and cancels, so it drops out. Typical opus numbers with a
~20k boot: **200k → ~2-3 turns, 120k → ~3-5, 80k → ~5-8**. So 200k with the goal one turn away →
*continue*; 120k with a day of work left → hand off. Sonnet's cache-read is 5x cheaper, so its
breakeven is 5x further out — the model in use is part of the answer.

The `UserPromptSubmit` hook computes this every prompt and stays **silent** (zero tokens) unless
context is past `CTX_WARN_AT` **and** the breakeven has fallen to `TURNS_WARN` turns or fewer, and
then only once per 20k of further growth. It is **advisory**: it never blocks a prompt, never pauses
work in flight. The request is answered first, then the agent says in one line which applies —
fewer turns left than the breakeven → finish the goal, then `/handoff`; more → `/handoff` + `/clear`
now.

Read it by hand with `load_handoff.py --context`:

```
context 99096 tokens | boot here ~40957 | claude-opus-5
USD 0.087 wasted per further turn vs a fresh session   (printed with a $ sign; written out here
                                                        because $0 in a skill body is substituted
                                                        with the slash-command's argument)
breakeven: /handoff + /clear wins if more than ~5 turns of work remain
```

**What is measured vs assumed.** From the transcript: current context, the model (→ its real prices,
from the cache widget's `prices.json`), and `boot` — this session's own first turn, i.e. what a
`/clear` here restarts from (system prompt + skills + injected handoff), which is 2x the usual guess
on a machine with skills loaded. Constants in `load_handoff.py`: `HANDOFF_OUT`, `REDERIVE`. Not
measurable at all: **how many turns of work remain** — the agent's estimate, and the only input the
hook asks for. The aim is a healthy signal, not an accounting figure: the decision only flips when
the estimate is off by a factor, so rough inputs are fine.

## Skills for the next session (optional section)

The `SessionStart` injector (`~/.claude/session_inject.py`) reads `## Skills` from the active
handoff and stacks those on top of the machine defaults in `~/.claude/session-inject.json`. So the
agent writing the handoff decides what the *resuming* agent boots with — one bullet per skill, bare
name (`navindex`), resolved to `~/.claude/<name>-activate.md` or `~/.claude/skills/<name>/SKILL.md`.
A full path works too. `- -caveman` drops a default for this project. Unknown names are ignored
silently, so a wrong guess never blocks boot.

Add a skill only when step 1 of *Next steps* actually needs it — every injected file is re-sent
every turn. Omit the section entirely (the normal case) and the defaults apply unchanged.
Defaults are managed separately: `python ~/.claude/session_inject.py --list|--add|--rm|--on|--off`.

## Effort recommendation

Reasoning is the one cost `/clear` does **not** cut: a fresh session with a heavy default burns
thinking on work that doesn't need it. Say it in **both** places — they do different jobs:

- **In the file** (`## Effort`, one line). Survives the `/clear`; the resuming session reads it and
  can hold itself to that depth even if the harness level was never touched.
- **In the closing message**, naming the model actually in use (the resume inherits it). Only the
  user can dial the harness setting, and only before they continue — so it has to be said out loud,
  not just filed.

Rules:
- **Judge step 1 of Next steps, not the session that just ended.** A hard debugging session often
  hands off to mechanical work, and vice versa.
- **Lowest rung that plausibly works.** Mechanical edits, applying a decision already taken, running
  a documented sequence, flattening output → low. Normal implementation with edge cases → medium.
  Only genuine unknowns earn high: an API behaving against its docs, irreversible or
  wide-blast-radius changes, a design choice not yet made.
- **The floor is comprehension, never the diff.** Low effort must still buy reading the flow the
  change touches and every caller of what it edits. If step 1 touches something widely called,
  medium — "it's one line" is not a reason to go lower. Cheap thinking is fine; cheap *reading* is
  how a confident wrong fix ships.
- **Name the escalation trigger**, so the next session can raise it mid-flight instead of paying up
  front: "high if X's error contradicts its docs".
- **Say when reasoning isn't the bottleneck at all** — if the loop is dominated by builds, network,
  a device, or a slow test suite, more thinking buys nothing. Say so in the same line.
- **Write it in the language the user speaks**, both in the file and in the message.
- Split mode → one recommendation per track, since the tracks rarely need the same level.

## Split mode — two agents at once (optional)

When the remaining work has a part that **monopolizes one resource** and a part that doesn't, you
can hand off to two agents running side by side. The user starts each one with "continue 1" /
"continue 2". Same `.handoff/` folder, one extra file per track:

- `active.md` becomes a **router + shared state** — it is the only file auto-loaded at boot, so it
  must stay small. It says which track file to read, carries the state both agents need (HEAD,
  environment, decisions already taken, hard rules), and nothing else.
- `track1.md`, `track2.md` — one per agent, same sections as the normal format (so `--open` still
  parses them) plus a **Territory** section (files it writes, files it must not touch) and a
  **Done** line the agent fills in when it finishes — that's what tells the merging track it can go.
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

### Closing a split (write this protocol into `active.md`, both agents need it at boot)

A track that finishes does **not** write `active.md` — two agents overwriting the router is exactly
the clobber the split was designed to avoid. Instead:

1. **Each track, when done**, appends its outcome to its own `trackN.md` (what shipped, what was
   dropped and why, what the next session needs) and commits it. Then it stops and says so.
2. **One track owns the merge** — name it in `active.md`, same single-owner logic as the resource;
   track 1 by default. It merges only after the other's file says it is done.
3. **At merge time the "don't read the other track" rule lifts** — merging requires reading both.
   The merging agent runs `/handoff` normally: `--archive` folds both track files into one archived
   handoff and clears them, then it writes a fresh single `active.md` from both outcomes.
4. **Then `/clear` and start one fresh session** off that handoff. Don't keep talking to either
   old agent: their context is half the picture, and the merged handoff already carries the whole.

If one track stalls or gets abandoned, the other still merges — it records the stalled track's state
as an open item instead of waiting.

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
  resume so that when *you* run `/clear`, nothing is lost. `/handoff -f` goes one step further and
  starts the *next* session for you (`--spawn`), but ending the current one is still your call.
