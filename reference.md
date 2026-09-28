<!-- ====================== BEGIN NAV INDEX ====================== -->
<!-- NAV INDEX — auto-generated symbol map (refresh via the navindex skill) -->
<!--   L10     193B  /handoff — reference (read on demand) -->
<!--   L15     2.7K  Context checkpoint (automatic) -->
<!--   L58     3.5K  Split mode — two agents at once (optional) -->
<!--   L111    1.1K  Navigate the history -->
<!--   L128    2.9K  Notes -->
<!-- ======================= END NAV INDEX ======================= -->

# /handoff — reference (read on demand)

Sections moved out of `SKILL.md` so that loading the skill stays small. `SKILL.md` lists what
is here; read only the section the current task needs.

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
work in flight. It prints a `systemMessage`, which only the user sees: the user decides whether to
`/clear`, and the nudge adds nothing to the model's context. (The earlier version injected it into
the model's context: in the tia project it fired 628 times, and peak context still had a median of 186k.)

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
  single-track handoff can't strand a track nobody routes to. While `plan.md` has an open `- [ ]`
  step it copies them but keeps them (an orchestrate worker may resume from one); delete by hand.

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
- `review.md` (optional) lives in the same folder, is versioned, and is written by the project,
  not by this skill. It is read at exactly one moment, `--archive`, and never at boot, so a
  checklist of any length costs nothing on ordinary turns. Keep it a procedure (numbered steps
  with a command to run), not a list of past findings: those belong in the project's own docs.
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
