---
name: handoff
description: Save a compact handoff of the current session (goal, state, decisions, next steps, key files) so you can /clear and resume cheaply, AND navigate past handoffs. The SessionStart hook auto-loads the active one on the next session. Use when switching tasks, before /clear, when context grows large (over ~150k tokens), when the user says "handoff"/"save state"/"/handoff", OR when the user asks what's still pending/open from before, to see handoff history, or to find something from a past session. Also writes a split handoff (router + one track file per agent) when the work is to continue on two agents running in parallel. With the `plan` argument (`/handoff plan`) it additionally opens an optional multi-session plan file whose steps each carry a verifiable "done when", so resuming means checking conditions instead of re-deriving what is already finished.
---

<!-- ====================== BEGIN NAV INDEX ====================== -->
<!-- NAV INDEX — auto-generated symbol map (refresh via the navindex skill) -->
<!--   L21    /handoff — save session state so `/clear` is free -->
<!--   L27    Steps -->
<!--   L76    Format (keep under ~80 lines — a resume cue, not a log) -->
<!--   L169   Levels: `standing.md` (persistent) · `plan.md` (optional) · `active.md` (this session) -->
<!--   L221   Plan mode — `/handoff plan` (optional) -->
<!--   L269   Context checkpoint (automatic) -->
<!--   L312   Skills for the next session (always write this section) -->
<!--   L325   Effort recommendation -->
<!--   L354   Split mode — two agents at once (optional) -->
<!--   L406   Navigate the history -->
<!--   L423   Notes -->
<!-- ======================= END NAV INDEX ======================= -->

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
   This step also **lifts a legacy `## Standing decisions` section out into `standing.md`** the
   first time it runs on an old handoff, and prints a prune nudge if `standing.md` is over its cap
   — act on both before writing the new file (see **Levels** below). An unfinished `plan.md` is
   left alone; a fully closed one is folded into the archive and cleared.
3. **Write** the active file (path from step 1) with the sections below — terse, high-signal, no
   transcript. Overwrite it (idempotent; one active handoff per project). Splitting the work
   across two agents that run at the same time → see **Split mode** below.
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

- **Budget: 8-12 pieces, at most ~12 000 chars of output.** The tool truncates the result at 50 000
  chars (Bash) or 30 000 (PowerShell), and a truncated result loses the pieces that came after the
  one that overflowed. Counting pieces (`wc -c`, `grep -c`, `git status --short`) cost 50-200 bytes
  each, so twenty of those still fit; a content sample costs 1-3 KB, so about ten do.
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
3. **Edit, never rewrite.** Close a step by flipping `[ ]` to `[x]` and adding the evidence line —
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
- **Find a past decision/context** → `load_handoff.py --grep <term>` — `standing.md` (labelled LIVE,
  since a current constraint outranks any past mention) plus archived handoffs mentioning `<term>`,
  with date + matching lines. Use to locate when something appeared without grepping by hand. A
  constraint that was *retired* is in git, not here: `git log -p .handoff/standing.md`.

(prefix each with `python "$HOME/.claude/skills/handoff/`)

## Notes
- **Where files live:** inside a git repo → `<repo>/.handoff/active.md`, versioned *with the
  project* (commit it so handoffs travel with the code). Outside any repo → `~/.claude/handoff/`
  (per machine). The choice is automatic, derived from the cwd by `handoff_file()`, so skill and
  hook always agree.
- `standing.md` lives beside `active.md` (same repo-local or per-machine store) and is versioned
  with the project, so a clone carries the constraints. It is auto-loaded at boot **independently**
  of the handoff — a project whose handoff was cleared still boots with its constraints.
- `plan.md` (plan mode) lives in the same folder and is versioned too, so an unfinished plan
  travels with the repo — which is what lets a second machine pick up at the frontier instead of
  guessing. `--plan-path` prints its path; `--open` resumes at its first open step.
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
