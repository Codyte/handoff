---
name: handoff
description: Save a compact handoff of the current session (goal, state, decisions, next steps, key files) so you can /clear and resume cheaply, AND navigate past handoffs. The SessionStart hook auto-loads the active one on the next session. Use when switching tasks, before /clear, when context grows large (over ~150k tokens), when the user says "handoff"/"save state"/"/handoff", OR when the user asks what's still pending/open from before, to see handoff history, or to find something from a past session. Also writes a split handoff (router + one track file per agent) when the work is to continue on two agents running in parallel. With the `plan` argument (`/handoff plan`) it additionally opens an optional multi-session plan file whose steps each carry a verifiable "done when", so resuming means checking conditions instead of re-deriving what is already finished.
---

<!-- ====================== BEGIN NAV INDEX ====================== -->
<!-- NAV INDEX — auto-generated symbol map (refresh via the navindex skill) -->
<!--   L19     511B  /handoff — save session state so `/clear` is free -->
<!--   L28     801B  Companion skill: navindex -->
<!--   L39     4.1K  Steps -->
<!--   L97     5.2K  Format (keep under ~80 lines — a resume cue, not a log) -->
<!--   L191    3.3K  Levels: `standing.md` (persistent) · `plan.md` (optional) · `active.md` (this session) -->
<!--   L243    2.9K  Plan mode — `/handoff plan` (optional) -->
<!--   L294    857B  Skills for the next session (always write this section) -->
<!--   L307    2.0K  Effort recommendation -->
<!--   L337    642B  On demand — `reference.md` (read only the section you need) -->
<!-- ======================= END NAV INDEX ======================= -->

# /handoff — save session state so `/clear` is free

Long sessions at large context are the #1 cost driver. `/clear` fixes that but loses the thread —
this skill removes that downside: it writes a terse resume cue that the **SessionStart hook auto-loads**
on the next session, so after `/clear` you continue from exactly where you left off.

**Argument `orchestrate`** (start or resume a master): read [`orchestrate.md`](orchestrate.md)
and follow it; nothing else in this file is part of the master loop.

## Companion skill: navindex

For repository navigation and index refreshes, use [Codyte/navindex](https://github.com/Codyte/navindex.git).
Reuse `~/.agents/skills/navindex` if present. If missing and needed, install with
`git clone https://github.com/Codyte/navindex.git "$HOME/.agents/skills/navindex"`, then read its
`SKILL.md`. On Windows the shared root is `$HOME\.agents\skills`; create it if absent. Do not
overwrite an existing directory or clone a separate copy per host; use a supported discovery
path or junction. If unavailable, save the handoff with direct file references and note any stale
indexes. Handoff itself is available at [Codyte/handoff](https://github.com/Codyte/handoff.git),
normally checked out at `~/.agents/skills/handoff`. Load companion instructions only when needed.

## Steps

0. **Ensure the hooks are installed** (makes the skill self-sufficient on a fresh machine —
   the skill only *writes*; the hooks are what *read* the handoff back and watch the context):
   ```
   python "$HOME/.claude/skills/handoff/load_handoff.py" --ensure-hook
   ```
   Idempotent: registers the hooks in `~/.claude/settings.json` only if missing, using this
   machine's own absolute path. `SessionStart` (matcher `startup|clear`) injects the handoff at
   boot — on resume/compact the context already carries the thread, so injecting there would waste
   tokens. `UserPromptSubmit --check-context` is the context checkpoint below;
   `PostToolUse --check-worker` is its twin inside orchestrate-mode workers, and the `worker` agent
   is installed to `~/.claude/agents/`. Older installs are migrated in place. No-op if already correct.
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
   This step also **lifts a legacy `## Standing decisions` section out into `standing.md`** the
   first time it runs on an old handoff, and prints a prune nudge if `standing.md` is over its cap
   — act on both before writing the new file (see **Levels** below). An unfinished `plan.md` is
   left alone; a fully closed one is folded into the archive and cleared.
   **If the project has `.handoff/review.md`, `--archive` prints it: run it now, before step 3,**
   and write its result where it says. It is the project's own end-of-session checklist (tia:
   harvest the session's CLI friction from telemetry and fix what is cheap), so each handoff
   improves the project instead of only summarizing it. Never injected at boot; absent → no-op.
3. **Write** the active file (path from step 1) with the sections below — terse, high-signal, no
   transcript. Overwrite it (idempotent; one active handoff per project). Splitting the work
   across two agents that run at the same time → see **Split mode** in `reference.md`.
   Write agent-facing handoff files in English (`active.md`, `standing.md`, `plan.md`, and track
   files), unless the user explicitly requests another language for those files. Preserve literal
   names, paths, commands, quoted output, and existing historical archives. Reply to the user in
   their language. This applies to new text; do not rewrite unrelated standing decisions.
   If `.handoff/plan.md` exists, **update it in the same breath** — tick the steps this session
   closed, each with the evidence that closed it. See **Plan mode** below; `/handoff plan` is what
   creates it in the first place.
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

## First call
<one read-only shell command that re-orients this project in a single call: the few things step 1
actually needs — git state, the open plan step, the file it edits — joined with `;` and labelled.
The resuming session runs this before anything else. Omit the section when the project has no real
orientation sweep>

## Open / blockers
- <questions or blockers, if any>

## Skills
- <skill name step 1 needs — auto-injected next session AND named back in the resume cue>
- -<name> <— a leading dash removes a machine default instead of adding one>

## Effort
<low|medium|high> for step 1 — <reason>. Raise if <trigger>.
```

### `## First call` — the resume sweep is one command, not ten

Every tool call re-sends the whole context, so the orientation sweep a fresh session fires on boot
(`git log`, `git status`, the plan, the folder maps, the file step 1 edits) is where the resume
gives back what `/clear` just saved: ten calls cost ten copies of the window. The handoff already
knows what the next session must look at, so it writes that sweep **as one command**.

Batching is not bulk. The point is to reach the frontier of what can be known **without** the
information still to be collected — one call goes as far as the dependencies allow, and stops
there. What decides each piece is whether step 1 needs it, never whether it fits.

**The target is total tokens; call count is only its proxy.** Many lean calls beat one bloated
batch: a call chain A-Z where every step is filtered costs less than A-C where one step dumps a file
nobody reads. When a piece would come back big, leave it out of the batch and fetch it later, filtered
— or not at all.

- **Budget and cap: follow the `onecall` skill** (§ The cap): the result overflows past ~30 000
  bytes in both shells and the whole result becomes a 2 KB preview. Counting pieces (`wc -c`,
  `grep -c`, `git status --short`) cost 50-200 bytes; a content sample costs 1-3 KB.
- **What `SessionStart` already injected does not go in the sweep.** Re-reading the `active.md` the
  hook has just loaded is the most expensive call available: full price, zero information.
- **Slice by marker, never by line number.** A line number has to come from an earlier call, which
  is exactly how one question becomes three; `sed -n '/^## Next steps/,/^## /p'` and
  `grep -n PATTERN -B 12 file` answer *where* and *what* in the same piece. Anchor on text that does
  not change: `- [ ]` becomes `- [x]` the moment a step is done, and the slice then returns nothing,
  silently.
- **A piece whose size you do not know gets `head -c 400`.** `cat` of a file you have not sized is
  how a sweep hits the truncation ceiling.
- **Choose, do not sweep.** A piece that step 1 does not need is noise the resume pays for on every
  turn afterwards. Four earned pieces beat twelve speculative ones — quantity is not quality. What
  decides is dependency, not subject: pieces unrelated to each other still belong in the same call,
  and only a value another piece produces earns a call of its own.
- **Join with `;` and label each piece by number** (`echo "=== 1 ==="`, `=== 2 ===`, `=== 2.1 ===`
  for a sub-piece), never `&&` — a missing file must not kill the rest of the batch.
- **Filter every piece** (`head`, `tail`, `cut`, `grep -n`, a summary flag). Trading ten calls for
  one giant dump is worse than the ten: the dump sticks in context and is re-sent every turn after.
- **Only independent pieces.** Anything that needs another piece's output stays out — and where a
  second pass is unavoidable, ask for a little more in the first pass instead of splitting it in two.
- **Read-only.** Never a build, a deploy, a migration or a write verb in a resume batch: it runs
  before the agent has read anything, including the constraints that say what must not be touched.
- **Real paths, runnable verbatim.** The value is that the resume does not have to work out what to
  look at first.

The same arithmetic applies during the session, not only at boot. The handoff carries it because
boot is where it is forgotten.

## Levels: `standing.md` (persistent) · `plan.md` (optional) · `active.md` (this session)

Files in `.handoff/`, injected at boot, with different lifecycles:

| | `standing.md` — **level 0** | `plan.md` — **level 0.5**, optional | `active.md` — **level 1** |
|---|---|---|---|
| Scope | the project, across all sessions | one undertaking, across N sessions | the session that just ended |
| Written | **edited in place**, only when a verdict changes | **edited in place**, one step at a time | overwritten every handoff |
| Archived | never — it *is* the carry-forward | when the last step closes | yes, on every handoff |
| Injected | always | **only while a step is open** | always |

Level 0 holds only verdicts that **still constrain future work**: a floor not to cross, an approach
already rejected with a measurement behind it, a rule about where fixes go, a trap in the
environment that will bite again. Everything narrative — what happened, what shipped, what's next —
is level 1.

**Never rewrite `standing.md` wholesale.** Use `Edit` to add one entry or retire one entry; a `Write`
of the whole file is exactly the reword-and-drift this split exists to prevent. When you retire an
entry, say so in that session's `## Decisions`, so the reversal is visible instead of silent.

**Prune it.** Every line is re-sent on every turn of every future session, and boot is the floor
`/clear` lands on — an ever-growing level 0 eats the saving this skill exists to produce. Cap is
~30 non-empty lines (`STANDING_CAP`); `--archive` prints a nudge past it. An executed decision is
history, not a constraint — drop it: retiring is safe because the entry survives in git
(`git log -p .handoff/standing.md`), and the session that took it is in `archive/`, reachable with
`--grep <term>`. Do not paste past decisions here in bulk: a dump of every decision ever made is
larger than the context it was meant to save.

**Don't duplicate the machine's memory store.** `~/.claude/.../memory/` holds who the user is and
cross-project preferences. `standing.md` holds constraints on *this repo's* work, and is versioned
with it, so a clone carries them. If a fact fits both, it belongs in memory, not here.

A project with no constraints yet has no `standing.md` — that's normal; create it the first time a
verdict actually binds future work.

### Resuming a handoff written in the old format

Old handoffs kept the standing decisions **inside** `active.md`, with the instruction to copy the
section forward verbatim. If the handoff you booted on has a `## Standing decisions` section, that
instruction is retired — the boot injection says so too, in one line, so the correction reaches you
even before this file does. What to do:

- **`standing.md` does not exist yet** → change nothing by hand. Step 2 (`--archive`) lifts the
  section out on the next handoff, and it is injected on its own from then on. Just **do not write
  that section into the new `active.md`**.
- **`standing.md` exists and the handoff still has the section** → the section is a stale duplicate.
  `standing.md` wins. Move any entry that exists *only* in the section into `standing.md` (with
  `Edit`), then drop the section. Never write it again.

Either way the section never appears in a handoff you write. A verdict that belongs at level 0 goes
into `standing.md` with a targeted `Edit`; everything else is level 1 prose.

## Plan mode — `/handoff plan` (optional)

`## Next steps` is one session's slice of the work. When the work is a **sequence that outlives the
session** — a migration, a phased build-out, a documented procedure run N times — the slice keeps
losing the frame: each resume re-derives which steps are already satisfied, and re-derivation is
where drift enters. Plan mode adds the frame as its own file.

**`/handoff plan` creates or reopens `.handoff/plan.md`.** From then on every `/handoff` updates it,
argument or not — a plan that only moves when someone remembers the magic word is worse than none.
Get the path with `load_handoff.py --plan-path`.

**The format is a checklist whose steps carry a verifiable condition, not a description:**

```markdown
# Plan · <undertaking> · opened <date>

Gate: `<command whose exit 0 is the acceptance>`     <- optional, one line
Recipe: `<path to the reusable procedure, if the plan is an instance of one>`

- [x] 1. <step> — done when: <condition someone else could check>
      evidence: <what actually closed it, with a date or a command output>
- [ ] 2. <step> — done when: <condition>
- [ ] 3. <step> — done when: <condition>
```

Three properties earn the extra file, and each one is a rule:

1. **`done when` is a condition, never a restatement of the step.** "done when: rebuild ALL PASS"
   works; "done when: the verbs are written" is the step again and checks nothing. This is what
   makes resuming idempotent — you *check* your way back to the frontier instead of re-reading.
2. **A closed step keeps its evidence and stays visible.** That is what stops the next session
   redoing it. Deleting done steps throws away the only proof the plan converged.
3. **Edit, never rewrite.** Close a step with `load_handoff.py --tick <step> "<evidence>"`, which
   flips `[ ]` to `[x]` and adds the evidence line in one call —
   same reason `standing.md` is never rewritten whole: a wholesale rewrite is where a `done when`
   quietly turns back into prose.

**Resuming:** the boot injection points at the first open step. Check its `done when` *before*
doing it — another session, or another machine, may already have satisfied it.

**Cost is self-limiting.** The plan is injected only while some step is `[ ]`; a fully ticked plan
stops being injected from that turn on, and the next `--archive` folds it into the archived handoff
and clears the file. No plan.md at all → nothing about the skill changes.

**Don't open a plan** for work that fits one session, for a list with no verifiable conditions (that
is `## Next steps`, and it is fine), or for a standing rule (`standing.md`). And don't restate the
plan's steps in the handoff: the plan owns the sequence, `## Next steps` owns this session's slice
of it — usually one line pointing at the current step.

**`/handoff orchestrate`** runs the open plan with long-running `worker` subagents under one master session: read [`orchestrate.md`](orchestrate.md) and follow it.

## Skills for the next session (always write this section)

Write one bullet per instruction or skill that the saved work actually needs next. A bare name
(`navindex`) or full path is allowed; `- -caveman` removes a machine default where that integration
supports defaults. Keep the list small: skill metadata and any loaded instruction add recurring
context cost.

The resume cue is deliberately conditional. It tells the next agent to load missing instructions
when it continues the saved handoff, but it does not claim that every client already injected the
full skill body. If the latest user request is unrelated to the saved work, those handoff-specific
skills must not be forced onto it. Claude Code may additionally resolve this section through its
optional `session_inject.py`; Codex can use its skill catalogue or read the named path explicitly.

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
- **Write the file in English and the closing message in the user's language**, unless the user
  explicitly requests another language for the file.
- Split mode → one recommendation per track, since the tracks rarely need the same level.

## On demand — `reference.md` (read only the section you need)
- **Context checkpoint**: how the `UserPromptSubmit` hook computes the handoff breakeven;
  `load_handoff.py --context` prints it by hand.
- **Split mode**: two agents at once (router `active.md` + `trackN.md`, one owner per exclusive
  resource, the closing protocol).
- **Navigate the history**: `--open` (live TODO), `--history` (digest of archived handoffs),
  `--grep <term>` (standing.md + archive).
- **Notes**: where the files live, the archive, `review.md`, a new machine, no secrets.
- **Orchestrate**: `orchestrate.md` (master loop, lanes, `scripts/merge_lane.py`).
