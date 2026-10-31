<!-- ====================== BEGIN NAV INDEX ====================== -->
<!-- NAV INDEX — auto-generated symbol map (refresh via the navindex skill) -->
<!--   L14     781B  Workers mode — `/handoff workers` -->
<!--   L26     829B  Prerequisites (check once, at the first boot) -->
<!--   L36     7.4K  The master loop -->
<!--   L132    1.8K  Reuse — a related step goes to the warm worker (user ruling 2026-10-16) -->
<!--   L158    2.0K  Concurrency — lanes -->
<!--   L182    1.1K  Stop rules -->
<!--   L197    1.1K  Master turns are the expensive ones -->
<!--   L212    740B  Anti-patterns -->
<!--   L222    986B  Measuring a run -->
<!-- ======================= END NAV INDEX ======================= -->

# Workers mode — `/handoff workers`

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
  agent with its own `.claude/agents/worker.md` (extra preloaded skills, project rules). Keep its
  `tools:` allowlist: every tool definition is re-read on each worker request. After the first
  spawn, `session_stats.py` should show the worker boot below the ~50k measured without it.
- Hooks and agent files load at session start: after installing them, `/clear` before orchestrating.

## The master loop

**Run the master at low effort.** The loop is mechanical, and every reasoning token it writes stays
in its context for the rest of the run (the pilot master's 41.7k output was mostly reasoning).
Thinking belongs in rulings.

1. **Boot.** Read the first open step of plan.md. Check its `done when` before anything else:
   another session or worker may have finished it. Satisfied → tick it with the evidence, next.
2. **Size it.** Work under ~20 tool calls → do it inline; a worker's boot costs more than that.
   Bigger → brief a worker. Too big for one worker → split it into disjoint lanes first.
   Measured (tia F123): a worker's context grows ~3k tokens per request, so one worker costs
   about n·boot + 1.5k·n² for n requests. A step heading past ~30 requests (4+ code items, 40+
   doc rows) is cheaper as two lanes; under ~25 the second boot and its re-reading eat the
   saving. F123's 48-request worker would have saved ~1.2M tokens split in two.
   **Pick the model** (Agent `model`; the agent file defaults to Sonnet). Calibrated 2026-10-18
   (tia C11-C13; prices per M in/out: Haiku 5.5 $0.10/$0.50 up to a 100k prompt and 5x above it,
   Sonnet 5.5 $2/$10, Opus 5.5 $4/$20). Artificial Analysis, all at High:
   | | Haiku | Sonnet | Opus |
   |---|---|---|---|
   | cost/task | $0.08 | $0.88 | $1.82 |
   | Terminal-Bench 4.0 | 22% | 44% | 57% |
   | cost per success | ~$0.36 | ~$2.00 | ~$3.20 |
   | output tokens/task | 55k (37k reasoning) | 37k | 36k |
   Haiku is still cheapest per success, even after a retry. That holds only when a failure is cheap
   to detect: the gate plus the master's diff read. Haiku thinks longer per task, so its saving
   comes from price, not from writing fewer tokens. The routing ladder:
   - **Haiku**: one or two files, an existing pattern to copy, under ~15 requests, so the run
     stays below 100k. Boot is ~45k, which leaves Haiku about 50k of working room. Its hook
     checkpoint fires at 85k. Measured: C11 had 11 calls and 48k tokens, with a correct diff.
     A gate failure gets one Haiku retry with the error. A second failure escalates to Sonnet.
   - **Sonnet** (default): normal coding lanes, several files, new tests. Measured: C12 took 27
     calls and 72k tokens, with a clean diff and its own gate run. C13 took 20 + 5 calls and needed
     two master round-trips: a doctor rule too broad, and an IO rewrite that broke `test-openness`.
     The master's review and gate caught both.
   - **Opus**: live Portal/device work, ambiguous design, shared code with many callers, or a
     lane Sonnet already failed twice. Opus scores only ~13 points above Sonnet at twice the
     price, so reserve it for work where a wrong guess costs more than the run.
   Cheap models make the master's verification mandatory, not optional: read the diff against the
   step's intent and run the gate yourself when the worker reports `gate: not run`.
3. **Brief** (40 lines max; the worker knows nothing else, CLAUDE.md and its agent file aside.
   Never restate those: lanes and report format are already loaded. Agent files
   load at session start, so a rule added to the agent file mid-run reaches this run's workers
   only through the brief). **Every brief carries the `Method:` line verbatim**, even when the
   agent file preloads `onecall`: a project's own `.claude/agents/worker.md` may drop it, and the
   line costs one line against a worker that fires one call per question. The line orders a full
   Read of the skill file, not a summary of it (user ruling 2026-10-27: a worker briefed with the
   summary alone followed the skill poorly in its transcript).
   ```
   Method: onecall. First tool call: Read ~/.claude/skills/onecall/SKILL.md in full (no offset or
     limit) and follow it for the whole step. Before each shell call, write the questions of that
     step, layer them by dependency, and run one bounded call per layer (`=== N ===` labels,
     joined with `;`, every piece capped with head/cut).
   Step: <plan step number and title>
   Goal: <one or two lines: the outcome, not the method>
   Done when: <verbatim from plan.md>
   Gate: <exact command; exit 0 = done>
   Lane: <resource | offline>  (offline = spawned with isolation: "worktree"; see Concurrency)
   Area: <files/folders it owns; entry points with path:line>
   Read first: <path:line ranges, never whole files; standing rules; prior track file if resuming>
   Do not touch: <files, resources, other tracks' territory>
   Recipe: <commit/push rules for this repo; build owner if a build is needed>
   Rulings so far: <any that bind this step>
   ```
4. **Spawn** `Agent(subagent_type: "worker", description: "w<step> <3 words>", prompt: <brief>)`.
   It runs in the background; end the turn. **Never poll** and never read its transcript: the
   completion notification brings the report.
5. **Verify** on the notification, in one shell call. Offline lane:
   `python <skill>/scripts/merge_lane.py <branch> --check "<gate> && <build> && <e2e specs>" --tick <N> "<evidence>" --push`
   (the step's e2e specs go inside `--check`, so merge, gate, e2e, tick and push are one call; a
   failing check stops before the tick)
   rebases when main moved (rerunning `--gate` inside the lane), prints commits, numstat and the
   deleted non-header lines, merges `--ff-only`, runs the check, unlinks junctions before removing
   the worktree, ticks the step and pushes; `--inspect` stops before the merge. In-place lane:
   the gate command, `git log --oneline -3`, `git status --short | head`, then
   `load_handoff.py --tick <N> "<evidence>"` (never two Edits: they echo the plan twice). When a shell proxy (e.g. RTK) rewrites `git`, check removed lines
   with the unproxied binary (`/usr/bin/env git diff ...`): a condensed diff once made a NAV INDEX
   regeneration look like deleted history. Then act on the report:
   - `DONE` + gate exit 0 + clean tree → tick the step (`- [x]` plus the evidence: commit, gate
     result). Delete a leftover `.handoff/track1.md` in the same commit. Next step, **reuse check
     first** (§ Reuse): a related next step goes to this worker, merged with `merge_lane.py --keep`.
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

## Reuse — a related step goes to the warm worker (user ruling 2026-10-16)

Before spawning for the next step, check every finished worker of this run. **Always reuse** one
whose context covers the step: same Area or files, a step that builds on its commits (a second half
of the same item, a fix of its own `open:` lines), or the same subject. A fresh worker re-reads
what the warm one already holds (boot ~44-50k plus re-deriving the Area); the warm one pays only
its current context per request.

- **Reuse** = `SendMessage(to: <worker>, message: <new brief>)`. The brief keeps the same format,
  but only the lines that changed (Step, Goal, Done when, Gate, new Area/Do-not-touch); "Read first"
  lists only what it has not read yet.
- **Offline lane:** merge the finished step with `merge_lane.py <branch> --keep ...` so the
  worktree, junctions and branch survive; after the ff merge the branch equals main, and the worker
  rebases onto main before its next report as usual. The last step of that worker merges without
  `--keep` (cleanup).
- **Reuse only when warm and lean:** within the cache hour of its last report and below its
  checkpoint (~200k, `WORKER_WARN_AT`). Past either, a fresh worker briefed with that worker's
  report and track file is cheaper.
- **Same model fits:** a step that needs a stronger model than the warm worker runs on (Sonnet
  worker, an Opus-grade step) gets a fresh worker; a lighter step may reuse a stronger worker.
- **Unrelated subject → fresh worker.** Measured: on a new subject fresh was 2.5-3x cheaper
  (§ loop step 5); relatedness is what makes reuse pay.
- Never reuse across lanes: a resource-lane worker stays in the main checkout and an offline one in
  its worktree.
- Record the choice in the dispatch line to the user (`reuse w<step>` or `fresh: <reason>`).

## Concurrency — lanes
- **One resource lane per exclusive resource**: a single-session API or device, a registered build
  output, a test database, a fixed port. Its worker is the only one that touches it.
- **Every other writer is an offline lane in its own git worktree**
  (`Agent(subagent_type: "worker", isolation: "worktree", ...)`): no shared working tree, build
  output or index. It builds and tests with the project's offline switches (project CLAUDE.md names
  them, and any gitignored input to junction in), commits on its branch, never pushes.
- **Pilot once per project** before trusting lanes: run the offline build in a worktree while the
  resource lane works. A test that grabs the shared resource (global mutex, port, registry key)
  shows up there; fix it first (tia 2026-09-27: a test held the live single-call mutex).
- **Merge-friendly edits**: disjoint Areas; additions go next to related code, never all at the end
  of a shared list; generated files are regenerated after a rebase, never hand-merged.
- **The master merges** with `scripts/merge_lane.py` (loop step 5): rebase the lane branch onto main, rerun the offline gate if main moved,
  then `merge --ff-only`. Git refuses rather than overwrite the resource lane's uncommitted files;
  a refused merge waits for its next commit. A rebase conflict only in `__navi__.md` maps or inside
  NAV INDEX headers is regenerated (navindex) and the rebase continues; any other conflict stops
  with its paths named, and the master reads and resolves it itself.
- **Master: run anything inside a lane worktree in a subshell** (`(cd <wt> && ...)`). A plain `cd`
  persists the shell's cwd there, and `merge_lane.py` then fails `worktree remove` with
  `Permission denied` (tia 2026-10-16, twice).
- Read-only workers need no worktree. Sequential steps stay sequential.
- Default cap: two offline lanes beside the resource lane; raise it when builds do not slow the
  resource lane. Each spawn costs a boot (~44k), so split only work that runs long.

## Stop rules
- **Worker**: the `PostToolUse --check-worker` hook adds `Worker checkpoint: ~Xk vs ~Yk fresh
  worker. More than ~N turns left: ...` to its context once handing off beats continuing, and
  never below ~200k (`WORKER_WARN_AT`): an efficient worker runs to 200k unstopped. The worker
  decides against its own remaining work; the master may overrule a stop with `Run to finish`.
- **Master**: `/handoff` at a worker boundary every 2-3 worker cycles, or sooner when
  `load_handoff.py --context` puts the breakeven at or below the turns left. With parallel lanes
  a boundary is rare (some lane is always running): hand off at the first moment no worker runs
  and the context is past ~120k, and keep the master lean meanwhile (`merge_lane.py`, `--tick`,
  short user updates). F123 ran 8 cycles in one master at a 132k mean. Drain first: stop
  dispatching and let running workers report, since a completion notification lands in the old
  session. plan.md already holds the ledger
  and rulings, so the handoff is short; ask the user to `/clear`, and the next master boots on the
  plan and resumes at step 1 of the loop.

## Master turns are the expensive ones
Each master request re-reads a window that only grows (Modbux 2026-10-31: 37 requests, mean
110k, 4 067k processed, 43% of the run beside 6 workers). A worker request costs about half.
- **Three master requests per step**: the verify call (step 5, which also ticks), the next spawn,
  and the one-line close after it. Anything beyond them is a request to justify.
- **A notification that leaves another worker running gets one line and no tool call.** Verify
  once, when the last worker the step waits on reports.
- **An environment trap goes to `standing.md` the moment it is found, and the next brief names
  its workaround.** The same run spent 5 master calls (~500k) on one inherited environment
  variable (`ELECTRON_RUN_AS_NODE=1`) before an e2e launched.
- **Worker rules go in `agents/worker.md`, not in every brief.** A brief line is paid on every
  worker request; the agent file is paid once per boot and reaches every worker.
- **No attribution trailer** in commits the master or a worker writes (`Co-Authored-By`,
  "Generated with"): it carries no information and is paid in every commit message read back.

## Anti-patterns
- A reviewer agent per task. The gate command is the review; the master reads `git diff --stat`.
- Spawning for small work, or one worker per trivial step: batch small steps into one brief.
- Reading worker transcripts or long outputs into the master. The report is 15 lines by contract.
- Re-dispatching a ticked step, or dispatching without checking `done when` first.
- Worker briefs that restate CLAUDE.md or the skill: it is already loaded; point to sections.
- Letting a worker ask the user. Nobody is there; it returns NEEDS_DECISION instead.
- Invoking `/handoff` only to start or resume a master: read this file directly; SKILL.md adds
  nothing the loop uses and stays in the master's context for the whole run.

## Measuring a run
`python scripts/session_stats.py ~/.claude/projects/<project-dir> --last N` profiles each session
and its workers: boot, mean and peak context per request, total tokens processed. Orchestration
paid off when master + workers processed less than a single session doing the same kind of work,
with each worker's mean context well under its peak. Pilot (tia F120, 2026-09-27): master mean
70.6k, G120 worker mean 97k, total 4.8M processed vs 6.0-16.9M for the single-session baseline.

Second run (tia F123, 2026-09-28, 8 workers: 6 offline lanes, 2 Portal): master 62 requests, mean
132k (8.2M); workers 28.0M; total 36.2M. Worker boot ~50k, of which ~15-20k is instructions and
the rest tool definitions a worker never calls, hence the `tools:` allowlist in `agents/worker.md`.
The master's excess came from loading SKILL.md to reach this file, closing each lane by hand
(~4 calls at ~130k; now `scripts/merge_lane.py`) and ticking the plan with Edits (now `--tick`).
