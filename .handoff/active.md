# Handoff · handoff skill · 2026-07-31

## Goal
Context checkpoint in the `handoff` skill: warn when handoff+clear pays off, without blocking the session.
Repo: `c:\Users\Carlos_Ortiz\.agents\skills\handoff` (= `.claude/skills/handoff`, junction — same
directory).

## State
- HEAD: f65c9f4 — nothing committed (the working tree accumulates this session **and** the one from
  2026-07-07: matcher `startup|clear`, age note at boot, `HEAD:` in the template, fail-closed on settings).
- Live state: the hooks are already written to the real `~/.claude/settings.json` (SessionStart + the
  new UserPromptSubmit). Session running in the VS Code extension UI (`CLAUDE_CODE_ENTRYPOINT=claude-vscode`).
- Done this session:
  - `--check-context` (UserPromptSubmit hook) + `--context` (manual read). Silent: only speaks if
    ctx ≥ `CTX_WARN_AT` 120k **and** breakeven ≤ `TURNS_WARN` 8 turns, once per 20k band
    (state in `~/.claude/.handoff_ctx_warn`). Never blocks; it really fired at 123k.
  - `breakeven()`: saving/turn = (ctx − boot) × cache-read price; one-off cost = ctx×cr +
    HANDOFF_OUT×out + REDERIVE×cw. Prices from the cache-widget `prices.json` (built-in fallback).
  - `boot_context()`: the session's own first turn (head of the transcript). Measures ~44k here.
  - Generic `_wire()`: `--ensure-hook` wires both hooks (migration/repair/fail-closed preserved).
  - `spawn_session()` / `--spawn` + `/handoff -f`: in VS Code it returns the shortcut (Ctrl+Shift+P >
    Claude Code: New Conversation); outside it opens a new console with `claude`.
  - Selftest green (breakeven, context_tokens, UserPromptSubmit entry). navindex regenerated.
- In progress: nothing.

## Decisions (and why)
- A fixed threshold does NOT decide — the breakeven in remaining turns does. 200k near the end = continue.
- Growth per turn cancels on both sides of the equation → left out of the model.
- Boot measured from the session's own transcript, not a median of 10 sessions (read 1.2MB/prompt,
  same result: 44k vs 41k). Explicit request: "saudável, não cirúrgico" (healthy, not surgical).
- Bug: `boot_context` read the TAIL of the file (77k, inflated) — what matters is the HEAD.
- Bug: `$0.087` in the SKILL.md body became the slash-command argument (came out `--spawn.087`);
  written as "USD 0.087". Beware of `$0`/`$1` in examples inside SKILL.md.
- Automatic `/clear` is impossible: skills/hooks don't invoke harness commands. The VS Code extension
  exposes `claude-vscode.newConversation`, but VS Code does not fire an extension command from the CLI
  and the extension registers no `vscode://` handler (activationEvents only `onStartupFinished` +
  webview). The most that can be automated = a user keybinding.
- Rejected (YAGNI): calibrating REDERIVE by measuring post-handoff sessions, breakeven in output
  tokens, counting `--open` items as a proxy for remaining work.

## Next steps (ordered)
1. Optional keybinding in VS Code's `keybindings.json`: key → `claude-vscode.newConversation`
   (the user picks the key; the `keybindings-help` skill covers the format).
2. `git add -A && git commit` (load_handoff.py, SKILL.md, README.md, __navi__.md, .handoff/);
   check that `.navindex-cache.json` is in .gitignore before the `-A`.

## Key files
- load_handoff.py:252 — `breakeven()`; :244 `boot_context()`; :277 `spawn_session()`;
  :320 `check_context()`; :172-177 constants (CTX_WARN_AT, TURNS_WARN, HANDOFF_OUT, REDERIVE).
- load_handoff.py:112 — `_wire()`; :147 `ensure_hook()` (both hooks).
- SKILL.md — section "Context checkpoint (automatic)"; step 4 with `/handoff -f` + VS Code note.
- __navi__.md — folder map, regenerated; read it before a broad search here.

## Open / blockers
- None. Only the pending commit (2 sessions accumulated).

## Effort
low for step 1 — edit a keybinding JSON with the key the user names; step 2 is mechanical. Raise
to medium if the commit requires touching .gitignore or if the real settings.json looks out of
place. Reasoning is not the bottleneck here.
