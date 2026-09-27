<!-- ====================== BEGIN NAV INDEX ====================== -->
<!-- NAV INDEX — auto-generated symbol map (refresh via the navindex skill) -->
<!--   L12     789B  Orchestrate mode — `/handoff orchestrate` -->
<!--   L24     633B  Prerequisites (check once, at the first boot) -->
<!--   L32     3.0K  The master loop -->
<!--   L76     497B  Concurrency -->
<!--   L83     699B  Stop rules -->
<!--   L93     568B  Anti-patterns -->
<!--   L101    501B  Measuring a run -->
<!-- ======================= END NAV INDEX ======================= -->

# Orchestrate mode — `/handoff orchestrate`

One **master** session works through `.handoff/plan.md` for hours by spawning long-running
**worker** subagents, one plan step each, and supervising them through short reports. It is plan
mode with the execution delegated: `plan.md` stays the ledger, split-mode track files are the
worker's handoff, and the context checkpoint is the stop rule on both sides.

Why this shape and not one agent per task plus a reviewer: every spawn boots a fresh context
(~44k measured for a worker), so per-task agents and reviewers multiply the fixed cost; a plan of
20 small steps done that way burns a quota before it ends. Workers here are few and long, the
master stays small because it only ever reads reports, and verification is the step's own gate.

## Prerequisites (check once, at the first boot)
- An open plan: `load_handoff.py --plan-path` exists with `- [ ]` steps that carry a `done when`.
  No plan → run `/handoff plan` first; orchestrating without a ledger re-dispatches finished work.
- `load_handoff.py --ensure-hook` prints `PostToolUse: already present` and `worker agent: present`
  (the worker's checkpoint hook and `~/.claude/agents/worker.md`). A project may override the
  agent with its own `.claude/agents/worker.md` (extra preloaded skills, project rules).
- Hooks and agent files load at session start: after installing them, `/clear` before orchestrating.

## The master loop

**Run the master at low effort.** The loop is mechanical, and every reasoning token it writes stays
in its context for the rest of the run (the pilot master's 41.7k output was mostly reasoning).
Thinking belongs in rulings.

1. **Boot.** Read the first open step of plan.md. Check its `done when` before anything else:
   another session or worker may have finished it. Satisfied → tick it with the evidence, next.
2. **Size it.** Work under ~20 tool calls → do it inline; a worker's boot costs more than that.
   Bigger → brief a worker.
3. **Brief** (40 lines max; the worker knows nothing else, CLAUDE.md aside):
   ```
   Step: <plan step number and title>
   Goal: <one or two lines: the outcome, not the method>
   Done when: <verbatim from plan.md>
   Gate: <exact command; exit 0 = done>
   Area: <files/folders it owns; entry points with path:line>
   Read first: <path:line ranges, never whole files; standing rules; prior track file if resuming>
   Do not touch: <files, resources, other tracks' territory>
   Recipe: <commit/push rules for this repo; build owner if a build is needed>
   Rulings so far: <any that bind this step>
   ```
4. **Spawn** `Agent(subagent_type: "worker", description: "w<step> <3 words>", prompt: <brief>)`.
   It runs in the background; end the turn. **Never poll** and never read its transcript: the
   completion notification brings the report.
5. **Verify** on the notification, in one shell call: the gate command, `git log --oneline -3`,
   `git status --short | head`. When a shell proxy (e.g. RTK) rewrites `git`, check removed lines
   with the unproxied binary (`/usr/bin/env git diff ...`): a condensed diff once made a NAV INDEX
   regeneration look like deleted history. Then act on the report:
   - `DONE` + gate exit 0 + clean tree → tick the step (`- [x]` plus the evidence: commit, gate
     result). Delete a leftover `.handoff/track1.md` in the same commit. Next step.
   - `DONE` but the gate fails or the tree is dirty → treat as `PARTIAL` with that as the open item.
   - `PARTIAL` → the worker wrote `.handoff/track1.md`. `SendMessage` the same worker inside the
     cache hour for a short same-subject follow-up, or after a checkpoint stop when its report shows
     efficient progress and the master judges the remaining track steps finish the step: the
     message says `Run to finish`, which overrides later checkpoint lines (user ruling 2026-09-27:
     finishing warm beats re-deriving). Anything else, a new subject or a worker far from done,
     gets a fresh worker whose brief is the track file plus the original Gate/Area/Do-not-touch
     lines. Measured: a 9-call follow-up at ~135k/request cost
     about what a fresh worker would; on a new subject fresh was 2.5-3x cheaper.
   - `NEEDS_DECISION` → rule it yourself and record it under the step in plan.md:
     `Ruling: <decision> — <why> — <cost if wrong>`; then resume the worker with the ruling.
     Only four kinds go to the user: irreversible, security, an outward side effect (publish, send,
     deploy, spend), or a plan that turned out wrong. Ask, and meanwhile run any independent step.
6. **Repeat** from 1. Commit plan.md ticks with explicit paths; never `git add -A` (a worker may
   be mid-edit in the same tree).

## Concurrency
- **One worker per exclusive resource at a time**: a single-session API or device, a build output,
  a test database, a fixed port. Name the owner in the brief; the other workers never touch it.
- A **read-only** worker (research, reflection, reading docs, drafting text into its own new file)
  may run beside the resource owner. Two writers in one tree only with disjoint `Area` lines.
- Sequential steps stay sequential: parallelism that needs a merge costs more than it saves.

## Stop rules
- **Worker**: the `PostToolUse --check-worker` hook adds `Worker checkpoint: ~Xk vs ~Yk fresh
  worker. More than ~N turns left: ...` to its context once handing off beats continuing, and
  never below ~200k (`WORKER_WARN_AT`): an efficient worker runs to 200k unstopped. The worker
  decides against its own remaining work; the master may overrule a stop with `Run to finish`.
- **Master**: `/handoff` at a worker boundary every 2-3 worker cycles, or sooner when
  `load_handoff.py --context` puts the breakeven at or below the turns left. Never while a worker
  runs: its completion notification lands in the old session. plan.md already holds the ledger
  and rulings, so the handoff is short; ask the user to `/clear`, and the next master boots on the
  plan and resumes at step 1 of the loop.

## Anti-patterns
- A reviewer agent per task. The gate command is the review; the master reads `git diff --stat`.
- Spawning for small work, or one worker per trivial step: batch small steps into one brief.
- Reading worker transcripts or long outputs into the master. The report is 15 lines by contract.
- Re-dispatching a ticked step, or dispatching without checking `done when` first.
- Worker briefs that restate CLAUDE.md or the skill: it is already loaded; point to sections.
- Letting a worker ask the user. Nobody is there; it returns NEEDS_DECISION instead.

## Measuring a run
`python scripts/session_stats.py ~/.claude/projects/<project-dir> --last N` profiles each session
and its workers: boot, mean and peak context per request, total tokens processed. Orchestration
paid off when master + workers processed less than a single session doing the same kind of work,
with each worker's mean context well under its peak. Pilot (tia F120, 2026-09-27): master mean
70.6k, G120 worker mean 97k, total 4.8M processed vs 6.0-16.9M for the single-session baseline.
