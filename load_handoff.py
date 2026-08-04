#!/usr/bin/env python3
"""Handoff loader/locator — shared by the /handoff skill and the SessionStart hook.

Two modes:
  python load_handoff.py --path     -> print the handoff file path for the current project (the
                                       /handoff skill writes there, so skill and hook always agree)
  python load_handoff.py            -> HOOK mode: read the SessionStart JSON on stdin, and if a
                                       handoff exists for that project, print it. A SessionStart
                                       hook's stdout is injected as context, so the next session
                                       (after /clear) resumes from the saved state automatically.
  python load_handoff.py --check-context -> HOOK mode (UserPromptSubmit): computes the handoff
                                       breakeven from the transcript and nudges once a handoff
                                       starts paying for itself. Silent otherwise (zero tokens).
  python load_handoff.py --context  -> print that breakeven for the current session, by hand.

Handoff files live in <repo>/.handoff/active.md when cwd is inside a git repo (versioned with the
project), else under ~/.claude/handoff/<sanitized-project-path>.md (per machine).

Two injected levels, opposite lifecycles: `standing.md` (level 0 — the project's persistent
constraints; edited in place, never archived, injected even with no active handoff) and
`active.md` (level 1 — one session; overwritten every handoff, archived first).
"""
# ====================== BEGIN NAV INDEX ======================
# NAV INDEX — auto-generated symbol map (refresh via the navindex skill)
#   L69    _key
#   L73    _git_root
#   L83    handoff_file
#   L95    track_files
#   L103   STANDING_CAP
#   L106   standing_file
#   L117   migrate_standing
#   L132   standing_status
#   L150   _archive_dir
#   L157   _archive_files
#   L164   _wire
#   L199   ensure_hook
#   L224   CTX_WARN_AT
#   L225   CTX_WARN_STEP
#   L226   TURNS_WARN
#   L227   BOOT_FALLBACK
#   L228   HANDOFF_OUT
#   L229   REDERIVE
#   L233   _PRICES
#   L238   prices
#   L249   _usage_lines
#   L270   _tail
#   L281   _head
#   L289   context_tokens
#   L296   boot_context
#   L304   breakeven
#   L329   spawn_session
#   L355   _warn_state
#   L372   check_context
#   L393   archive_current
#   L420   _section
#   L427   history
#   L447   open_items
#   L463   grep
#   L475   _selftest
#   L585   boot_breakdown
#   L625   main
# ======================= END NAV INDEX =======================

import sys, os, json, re, pathlib, datetime

# Windows consoles default to cp1252; handoff text (accents, em-dashes) would crash on print.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _key(cwd):
    return re.sub(r"[^A-Za-z0-9]+", "_", os.path.abspath(cwd)).strip("_") or "root"


def _git_root(cwd):
    """Walk up to the enclosing git repo root, or None if cwd is not inside a repo.
    When inside a repo the handoff lives there so it is versioned with the project."""
    p = pathlib.Path(os.path.abspath(cwd))
    for d in (p, *p.parents):
        if (d / ".git").exists():
            return d
    return None


def handoff_file(cwd):
    root = _git_root(cwd)
    if root is not None:
        d = root / ".handoff"            # versioned with the project → joins its git
        d.mkdir(parents=True, exist_ok=True)
        return d / "active.md"           # one active handoff per repo; path implies the project
    # ponytail: outside a repo, keep the per-machine global store (no scatter of .handoff/ dirs)
    d = pathlib.Path(os.path.expanduser("~")) / ".claude" / "handoff"
    d.mkdir(parents=True, exist_ok=True)
    return d / (_key(cwd) + ".md")


def track_files(cwd):
    """Per-track handoffs (`track1.md`, `track2.md`, …) next to the active one, when the work was
    split across agents that run at the same time. Empty list = ordinary single-track handoff.
    Only active.md is auto-loaded at boot; it routes each agent to its own track file."""
    d = handoff_file(cwd).parent
    return sorted(d.glob("track*.md"))


STANDING_CAP = 30            # non-empty lines; past this, --archive nudges to prune (see below)


def standing_file(cwd):
    """Level 0 — the project's persistent constraints, next to the active handoff.

    A handoff describes ONE session and is rewritten every time; these verdicts outlive all of
    them. Keeping them in their own file means /handoff never rewrites them, so a constraint
    cannot be silently reworded, shortened or dropped by a copy-forward — which is the failure
    this split exists to remove. Injected at boot ahead of the session handoff, and independently
    of it (a project with no active handoff still boots with its constraints)."""
    return handoff_file(cwd).parent / "standing.md"


def migrate_standing(cwd, txt):
    """One-time lift: older handoffs carried '## Standing decisions' INSIDE active.md, copied
    verbatim each session. On the first archive after this upgrade, move it out — no manual step,
    no lost verdicts. `txt` is the outgoing handoff's text. No-op once standing.md exists."""
    dest = standing_file(cwd)
    if dest.exists():
        return False
    body = _section(txt, "Standing decisions")
    if not body:
        return False
    dest.write_text("# Standing decisions — persistent constraints for this project\n\n"
                    + body + "\n", encoding="utf-8")
    return True


def standing_status(cwd):
    """Nudge when standing.md outgrows its cap — returned at HANDOFF time, never at boot.

    Boot is the floor /clear lands on, and every line here is re-sent on every turn of every
    future session, forever. So the file has to be pruned, not accumulated. Warning at boot would
    itself cost tokens every turn; warning at handoff time reaches the agent at the one moment it
    is both looking at the decisions and able to retire them."""
    f = standing_file(cwd)
    if not f.exists():
        return None
    n = len([ln for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()])
    if n <= STANDING_CAP:
        return None
    return (f"standing.md: {n} non-empty lines (cap {STANDING_CAP}) — re-sent every turn of every "
            f"future session. Retire entries whose work is done (the archive keeps them) before "
            f"writing this handoff.")


def _archive_dir(cwd):
    base = handoff_file(cwd).parent
    # global store mixes every project → keep per-project subfolders; a project-local store is
    # already scoped to one repo → archive sits directly under it.
    return base / "archive" / _key(cwd) if _git_root(cwd) is None else base / "archive"


def _archive_files(cwd):
    """Sorted archived handoff files (filename = timestamp = sort key), or []. Single source for
    the archive glob shared by history() and grep()."""
    arc_dir = _archive_dir(cwd)
    return sorted(arc_dir.glob("*.md")) if arc_dir.exists() else []


def _wire(data, event, matcher, cmd):
    """Idempotently put `cmd` in hooks.<event>, under `matcher` (None = no matcher key).
    Returns a short status string. Mutates `data`."""
    ss = data.setdefault("hooks", {}).setdefault(event, [])
    for entry in ss:
        if not isinstance(entry, dict):
            continue
        # match by filename+flags → finds our entry even after a moved home dir or skill folder
        ours = [h for h in entry.get("hooks") or [] if isinstance(h, dict)
                and "load_handoff.py" in (h.get("command") or "")
                and ("--check-context" in h["command"]) == ("--check-context" in cmd)]
        if not ours:
            continue
        if entry.get("matcher") == matcher and all(h["command"] == cmd for h in ours):
            return f"{event}: already present"
        for h in ours:
            h["command"] = cmd                   # repair a stale path from a moved install
        if len(entry["hooks"]) == len(ours):
            if matcher is None:
                entry.pop("matcher", None)
            else:
                entry["matcher"] = matcher       # entry is only ours → matcher in place
        else:
            # shared entry (other commands ride in it): move our command to its own entry so
            # the matcher does not silently restrict hooks that are not ours
            entry["hooks"] = [h for h in entry["hooks"] if h not in ours]
            ss.append({"hooks": ours} if matcher is None else {"matcher": matcher, "hooks": ours})
        return f"{event}: repaired"
    new = {"hooks": [{"type": "command", "command": cmd}]}
    if matcher is not None:
        new["matcher"] = matcher
    ss.append(new)
    return f"{event}: wired"


def ensure_hook(settings=None):
    """Idempotently register the two hooks this skill needs:
      SessionStart (matcher startup|clear) → injects the active handoff at boot.
      UserPromptSubmit --check-context     → nudges to /handoff once context gets expensive.
    The skill (writer) and these hooks (readers) are separate pieces; copying the skill folder to a
    new machine does NOT bring them. Running this once on a machine wires them. Writes THIS file's
    absolute path → each machine self-registers a command valid for its own home dir (no hardcoded
    username); rerunning after a moved skill folder repairs the stored path.
    SessionStart matcher: on resume/compact the context already carries the thread, so firing there
    would re-inject the handoff for nothing. Pre-matcher installs are migrated in place."""
    settings = settings or pathlib.Path(os.path.expanduser("~")) / ".claude" / "settings.json"
    base = f'python "{os.path.abspath(__file__)}"'
    try:
        data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
        msgs = [_wire(data, "SessionStart", "startup|clear", base),
                _wire(data, "UserPromptSubmit", None, base + " --check-context")]
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except Exception:
        # fail closed: unreadable JSON or an unexpected shape must never corrupt settings.json
        print("settings.json unreadable or unexpected shape — left untouched; add the hooks by hand")
        return
    print(" | ".join(msgs) + f" -> {base}")


CTX_WARN_AT = 120_000        # floor: below this a nudge is noise even if breakeven says otherwise
CTX_WARN_STEP = 20_000       # re-warn only after this much further growth (one nudge per band)
TURNS_WARN = 8               # nudge once handoff pays for itself within this many remaining turns
BOOT_FALLBACK = 20_000       # assumed post-/clear context when this project has no measured one
HANDOFF_OUT = 2_000          # output tokens the handoff turn itself writes
REDERIVE = 8_000             # tokens the fresh session re-reads to get back on the thread (cache-write)

# USD per token: cache-read / cache-write / output. Matched by substring of the model id, same
# table the cache widget bills from — read its prices.json when present so there is one source.
_PRICES = {"opus":   {"cr": 1.50, "cw": 18.75, "out": 75.0},
           "sonnet": {"cr": 0.30, "cw": 3.75,  "out": 15.0},
           "haiku":  {"cr": 0.10, "cw": 1.25,  "out": 5.0}}


def prices(model):
    try:
        p = pathlib.Path(os.path.expanduser("~")) / ".claude" / "claude-cache-widget" / "prices.json"
        table = json.loads(p.read_text(encoding="utf-8")).get("models") or _PRICES
    except Exception:
        table = _PRICES
    row = next((v for k, v in table.items() if k in str(model or "").lower()), None) \
        or table.get("opus") or next(iter(table.values()))
    return {k: row[k] / 1e6 for k in ("cr", "cw", "out")}


def _usage_lines(text):
    """(input-side tokens, model) per non-sidechain assistant turn in `text`, in file order."""
    out = []
    for line in text.splitlines():
        if '"usage"' not in line:
            continue
        try:
            obj = json.loads(line)
            if obj.get("isSidechain"):        # sub-agent turns have their own context
                continue
            msg = obj.get("message") or {}
            u = msg.get("usage") or {}
            n = sum(int(u.get(k) or 0) for k in
                    ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            if n:
                out.append((n, msg.get("model")))
        except Exception:
            continue
    return out


def _tail(path, nbytes=262_144):
    """Last nbytes of a file as text — transcripts get large and this runs on every prompt."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - nbytes))
            return f.read().decode("utf-8", "replace")
    except Exception:
        return ""


def _head(path, nbytes=262_144):
    try:
        with open(path, "rb") as f:
            return f.read(nbytes).decode("utf-8", "replace")
    except Exception:
        return ""


def context_tokens(transcript):
    """Current context size in tokens = the last assistant turn's input side (fresh + cached).
    Read from the real usage numbers the transcript records, same source the cache widget uses."""
    lines = _usage_lines(_tail(transcript))
    return lines[-1][0] if lines else None


def boot_context(transcript):
    """What a /clear here restarts from: this session's own FIRST assistant turn (system prompt +
    skills + any injected handoff). Head of the same file we already read — no scan of past
    sessions; a rough number in the right order of magnitude is all the breakeven needs."""
    lines = _usage_lines(_head(transcript, 131_072))
    return lines[0][0] if lines else BOOT_FALLBACK


def breakeven(transcript):
    """How many more turns of work must remain for /handoff + /clear to be cheaper than continuing.

    Per turn, continuing re-sends the whole context: ctx x cache-read. After a handoff the same
    turn costs boot x cache-read, so each turn saves (ctx - boot) x cache-read. Growth per turn
    happens on both sides and cancels. Against that saving stands the one-off cost of the switch:
    the handoff turn itself (read the full context + write the file) plus what the fresh session
    re-reads to get back on the thread.
        turns = (ctx*cr + HANDOFF_OUT*out + REDERIVE*cw) / ((ctx - boot) * cr)
    Fewer turns remaining than that -> finishing here is the cheap move, however big the context."""
    lines = _usage_lines(_tail(transcript))
    if not lines:
        return None
    ctx, model = lines[-1]
    boot = boot_context(transcript)
    p = prices(model)
    if ctx <= boot:
        return None
    cost = ctx * p["cr"] + HANDOFF_OUT * p["out"] + REDERIVE * p["cw"]
    saving = (ctx - boot) * p["cr"]
    return {"ctx": ctx, "boot": boot, "model": model or "?",
            "turns": max(1, round(cost / saving)),
            "usd_per_turn_saved": round(saving, 4)}


def spawn_session(cwd=None):
    """Open a NEW Claude Code session in `cwd`, in its own console window. The SessionStart hook
    injects the handoff there, so it boots on the thread. This is the closest thing to an automatic
    /clear: the harness's own commands are not callable from a skill or a hook, so the old session
    has to be ended by the user — but the new one is already up and warm."""
    import shutil, subprocess
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "claude-vscode":
        # In the VS Code extension a spawned console would be a *different* UI, not a new tab in
        # the one being used — and VS Code exposes no way to fire an extension command from
        # outside. So hand the user the one keystroke that does it there.
        return ("running in the VS Code extension — spawning a console session would land outside "
                "this UI. Open the next one with Ctrl+Shift+P > 'Claude Code: New Conversation' "
                "(or 'Open in New Tab'); it boots with the handoff. Bind claude-vscode."
                "newConversation to a key to make it one keystroke.")
    exe = shutil.which("claude")
    if not exe:
        return "claude not found on PATH — start the new session by hand"
    cwd = cwd or os.getcwd()
    try:
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)   # 0 on POSIX → same terminal
        subprocess.Popen([exe], cwd=cwd, creationflags=flags, close_fds=True)
    except Exception as e:
        return f"could not spawn a session ({e}) — start it by hand"
    return f"new session started in {cwd} — it boots with the handoff; /clear or close this one"


def _warn_state(session, band=None):
    """Last warned band per session, in ~/.claude/.handoff_ctx_warn. Read with band=None."""
    p = pathlib.Path(os.path.expanduser("~")) / ".claude" / ".handoff_ctx_warn"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if band is None:
        return data.get(session, 0)
    try:
        # keep the file from growing forever: only the 20 most recent sessions
        data[session] = band
        p.write_text(json.dumps(dict(list(data.items())[-20:])), encoding="utf-8")
    except Exception:
        pass


def check_context(payload):
    """UserPromptSubmit hook: nudge when a handoff would pay for itself soon. Silent (zero tokens)
    below the floor, above the breakeven horizon, and inside an already-warned band — so the
    reminder lands once per 20k of growth, not on every prompt. Advisory: it never blocks."""
    b = breakeven(payload.get("transcript_path") or "")
    if not b or b["ctx"] < CTX_WARN_AT or b["turns"] > TURNS_WARN:
        return
    band = b["ctx"] // CTX_WARN_STEP
    session = payload.get("session_id") or "?"
    if band <= _warn_state(session):
        return
    _warn_state(session, band)
    print(f"# Context checkpoint (advisory, not a stop): ~{b['ctx']//1000}k tokens, "
          f"${b['usd_per_turn_saved']:.2f}/turn wasted vs a fresh session "
          f"(boot here measures ~{b['boot']//1000}k).\n"
          f"/handoff + /clear pays for itself if MORE THAN ~{b['turns']} turns of work remain.\n"
          f"Answer the user first, then say in one line: fewer turns left than that → finish the\n"
          f"goal, then /handoff; more → suggest /handoff + /clear now. Never abandon work in\n"
          f"flight for this — it is a cost hint, never a reason to refuse or pause a task.")


def archive_current(cwd):
    """Move the current active handoff into a chronological, on-demand archive before it gets
    overwritten. One file per handoff (filename = timestamp = sort key). The archive is NEVER
    auto-loaded by the hook, so boot stays lean — it's a write-only history you Read on demand."""
    active = handoff_file(cwd)
    if not active.exists():
        return None
    txt = active.read_text(encoding="utf-8").strip()
    if not txt:  # empty stub — nothing worth keeping
        return None
    # Track files are part of the same handoff: fold them into the one archived file, then drop
    # them. Leaving them behind would strand a stale track the next router no longer points at.
    tracks = track_files(cwd)
    for t in tracks:
        body = t.read_text(encoding="utf-8").strip()
        if body:
            txt += f"\n\n<!-- ===== {t.name} ===== -->\n\n{body}"
    arc_dir = _archive_dir(cwd)
    arc_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")
    dest = arc_dir / (stamp + ".md")
    dest.write_text(txt + "\n", encoding="utf-8")
    for t in tracks:
        t.unlink()
    return dest


def _section(txt, head):
    """Return the body lines of a '## <head>' section, until the next '## ' or EOF."""
    m = re.search(r"^##\s+" + re.escape(head) + r"\b.*?\n(.*?)(?=^##\s|\Z)",
                  txt, re.S | re.M)
    return m.group(1).strip() if m else ""


def history(cwd):
    """Chronological digest of the archive: per past handoff, its Goal + Next steps +
    Open/blockers — the 'what was pending over time' view, derived on the fly from existing
    files so there is no second index to keep in sync and zero boot cost (Read on demand)."""
    files = _archive_files(cwd)
    if not files:
        return "(no archived handoffs yet)"
    out = []
    for f in files:
        txt = f.read_text(encoding="utf-8")
        goal = " ".join(_section(txt, "Goal").split()) or "(no Goal)"
        out.append(f"## {f.stem}\n**Goal:** {goal}")
        for head in ("Next steps", "Open / blockers"):
            body = _section(txt, head)
            if body:
                out.append(f"**{head}:**\n{body}")
        out.append("")
    return "\n".join(out).strip()


def open_items(cwd):
    """The live TODO: Next steps + Open/blockers of the ACTIVE handoff — current pending state in
    one read. Reflects when the handoff was written; cross-check against live state (git/.env)."""
    def pending(txt, label=""):
        pre = f"[{label}] " if label else ""
        return [f"**{pre}{h}:**\n{b}" for h in ("Next steps", "Open / blockers")
                if (b := _section(txt, h))]

    f = handoff_file(cwd)
    parts = pending(f.read_text(encoding="utf-8") if f.exists() else "")
    # a split handoff keeps the real TODO in the track files; active.md is just the router
    for t in track_files(cwd):
        parts += pending(t.read_text(encoding="utf-8"), t.stem)
    return "\n\n".join(parts) or "(no active handoff, or nothing open)"


def grep(cwd, term):
    """Print archived handoffs whose text contains <term> (case-insensitive), with date + the
    matching lines — find when a decision/context appeared without grepping N paths by hand."""
    out = []
    for f in _archive_files(cwd):
        hits = [ln for ln in f.read_text(encoding="utf-8").splitlines()
                if term.lower() in ln.lower()]
        if hits:
            out.append(f"## {f.stem}\n" + "\n".join(hits))
    return "\n\n".join(out) or f"(no archived handoff mentions {term!r})"


def _selftest():
    """Self-check for the non-trivial bit: _section() boundary parsing. Run: --selftest."""
    sample = ("# H\n## Goal\ng1\ng2\n## Next steps\n1. a\n2. b\n"
              "## Open / blockers\n- x\n## Key files\n- f.py\n")
    assert _section(sample, "Goal") == "g1\ng2", _section(sample, "Goal")
    assert _section(sample, "Next steps") == "1. a\n2. b"
    assert _section(sample, "Open / blockers") == "- x"   # '/' is escaped, not regex
    assert _section(sample, "Missing") == ""              # absent section → empty
    assert _section("", "Goal") == ""                     # empty input → empty
    # ensure_hook: fresh install gets the matcher; a pre-matcher install is migrated in place.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        s = pathlib.Path(td) / "settings.json"
        ensure_hook(s)
        ss = json.loads(s.read_text(encoding="utf-8"))["hooks"]["SessionStart"]
        assert ss[0]["matcher"] == "startup|clear", ss
        ups = json.loads(s.read_text(encoding="utf-8"))["hooks"]["UserPromptSubmit"]
        assert "matcher" not in ups[0] and "--check-context" in ups[0]["hooks"][0]["command"], ups
        del ss[0]["matcher"]
        s.write_text(json.dumps({"hooks": {"SessionStart": ss}}), encoding="utf-8")
        ensure_hook(s)
        ss = json.loads(s.read_text(encoding="utf-8"))["hooks"]["SessionStart"]
        assert len(ss) == 1 and ss[0]["matcher"] == "startup|clear", ss
        ensure_hook(s)  # third run: already correct → no-op
        # shared pre-matcher entry: our command moves to its own entry, the rider stays unrestricted
        rider = {"type": "command", "command": "python other.py"}
        shared = {"hooks": [ss[0]["hooks"][0], rider]}
        s.write_text(json.dumps({"hooks": {"SessionStart": [shared]}}), encoding="utf-8")
        ensure_hook(s)
        ss = json.loads(s.read_text(encoding="utf-8"))["hooks"]["SessionStart"]
        assert ss[0]["hooks"] == [rider] and "matcher" not in ss[0], ss
        assert ss[1]["matcher"] == "startup|clear" and "load_handoff" in json.dumps(ss[1]), ss
        # stale command path (moved skill folder) is repaired on rerun, even with matcher present
        ss[1]["hooks"][0]["command"] = 'python "/old/gone/load_handoff.py"'
        s.write_text(json.dumps({"hooks": {"SessionStart": ss}}), encoding="utf-8")
        ensure_hook(s)
        ss = json.loads(s.read_text(encoding="utf-8"))["hooks"]["SessionStart"]
        assert ss[1]["hooks"][0]["command"] == f'python "{os.path.abspath(__file__)}"', ss
        # unexpected shape (valid JSON, wrong structure) → fail closed, file untouched
        s.write_text('{"hooks": null}', encoding="utf-8")
        ensure_hook(s)
        assert s.read_text(encoding="utf-8") == '{"hooks": null}'
    # split mode: --open reaches into the track files, --archive folds them in and clears them
    with tempfile.TemporaryDirectory() as td:
        (pathlib.Path(td) / ".git").mkdir()      # repo-local store, not the global one
        d = pathlib.Path(td) / ".handoff"
        d.mkdir()
        (d / "active.md").write_text("# H\n## Goal\nrouter\n", encoding="utf-8")
        (d / "track1.md").write_text("# T1\n## Next steps\n1. portal\n", encoding="utf-8")
        (d / "track2.md").write_text("# T2\n## Open / blockers\n- none\n", encoding="utf-8")
        assert sorted(f.name for f in track_files(td)) == ["track1.md", "track2.md"]
        out = open_items(td)
        assert "[track1] Next steps" in out and "[track2] Open / blockers" in out, out
        arc = archive_current(td)
        body = arc.read_text(encoding="utf-8")
        assert "1. portal" in body and "- none" in body, body   # tracks folded into the archive
        assert not track_files(td)                              # …and cleared, never stranded
    # level 0: the section is lifted out of the handoff exactly once, survives --archive, and only
    # nags about size once past the cap
    with tempfile.TemporaryDirectory() as td:
        (pathlib.Path(td) / ".git").mkdir()
        d = pathlib.Path(td) / ".handoff"
        d.mkdir()
        old = "# H\n## Goal\ng\n## Standing decisions (carry forward verbatim)\n- rule A\n## Skills\n- x\n"
        (d / "active.md").write_text(old, encoding="utf-8")
        assert standing_status(td) is None                    # no standing.md yet → silent
        assert migrate_standing(td, old) is True
        assert "- rule A" in standing_file(td).read_text(encoding="utf-8")
        assert migrate_standing(td, old) is False             # idempotent: never re-lifts/clobbers
        assert standing_status(td) is None                    # 3 lines, well under the cap
        standing_file(td).write_text("\n".join(f"- r{i}" for i in range(STANDING_CAP + 1)),
                                     encoding="utf-8")
        assert "cap" in (standing_status(td) or "")           # over cap → prune nudge
        archive_current(td)
        assert standing_file(td).exists()                     # archiving must never eat level 0
        # a project that never had the section gets no standing.md invented for it
        with tempfile.TemporaryDirectory() as td2:
            (pathlib.Path(td2) / ".git").mkdir()
            assert migrate_standing(td2, "# H\n## Goal\ng\n") is False
            assert not standing_file(td2).exists()
    # context_tokens: last non-sidechain usage line wins, all three input fields summed
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td) / "t.jsonl"
        t.write_text(
            json.dumps({"message": {"usage": {"input_tokens": 1}}}) + "\n"
            + json.dumps({"message": {"usage": {"input_tokens": 5, "cache_read_input_tokens": 90,
                                               "cache_creation_input_tokens": 5,
                                               "output_tokens": 999}}}) + "\n"
            + json.dumps({"isSidechain": True,
                          "message": {"usage": {"input_tokens": 77}}}) + "\n",
            encoding="utf-8")
        assert context_tokens(t) == 100, context_tokens(t)       # output_tokens excluded
        assert context_tokens(pathlib.Path(td) / "nope.jsonl") is None
    # breakeven: more context → fewer remaining turns needed for a handoff to pay off; and a
    # context barely above boot never pays off (guarded, no divide-by-~0 blowup)
    with tempfile.TemporaryDirectory() as td:
        def mk(name, ctx):
            def row(n):
                return json.dumps({"message": {"model": "claude-opus-5",
                                               "usage": {"cache_read_input_tokens": n}}})
            p = pathlib.Path(td) / name
            p.write_text(row(20_000) + "\n" + row(ctx) + "\n", encoding="utf-8")
            return breakeven(p)
        big, small = mk("a.jsonl", 200_000), mk("b.jsonl", 120_000)
        assert big["boot"] == 20_000, big                   # first turn of the session, not last
        assert 1 <= big["turns"] < small["turns"], (big, small)
        assert mk("c.jsonl", 20_000) is None                # at boot → nothing left to save
    print("selftest ok")


def boot_breakdown(cwd, b):
    """Boot is the floor `/clear` lands on, so it caps everything this skill can save — and the
    `## Skills` section raises it. Size the files we control (chars/4; good enough to rank them);
    everything else is harness (system prompt, tool schemas, skill catalogue) and not ours to cut."""
    home = pathlib.Path(os.path.expanduser("~")) / ".claude"
    parts = [("handoff", handoff_file(cwd)),
             ("standing decisions", standing_file(cwd)),
             ("CLAUDE.md (global)", home / "CLAUDE.md"),
             ("CLAUDE.md (project)", pathlib.Path(cwd) / "CLAUDE.md")]
    try:
        sec = _section(handoff_file(cwd).read_text(encoding="utf-8", errors="replace"), "Skills")
        names = [ln.strip()[1:].strip() for ln in sec.splitlines()
                 if ln.strip().startswith(("-", "*"))]
        for n in names:
            if not n or n.startswith(("<", "-")):
                continue
            for cand in (home / f"{n}-activate.md", home / "skills" / n / "SKILL.md"):
                if cand.exists():
                    parts.append((f"skill: {n}", cand))
                    break
    except Exception:
        pass
    rows, known = [], 0
    for label, p in parts:
        try:
            t = len(p.read_text(encoding="utf-8", errors="replace")) // 4
        except Exception:
            continue
        known += t
        rows.append(f"  {label:22} ~{t:6} tok")
    price = b["usd_per_turn_saved"] / max(b["ctx"] - b["boot"], 1)   # USD per token per turn
    out = ["", f"boot floor ~{b['boot']} tok — /clear lands here, not at zero. Of it:"]
    out += rows
    out.append(f"  {'harness (not yours)':22} ~{max(b['boot'] - known, 0):6} tok"
               "  system prompt + tool schemas + skill catalogue")
    out.append(f"every 1k added to `## Skills` costs ~${price * 1000:.4f}/turn forever and pushes "
               f"the breakeven past {b['turns']} turns.")
    return "\n".join(out)


def main():
    if "--selftest" in sys.argv:
        _selftest()
        return
    if "--ensure-hook" in sys.argv:
        ensure_hook()
        return
    if "--path" in sys.argv:
        print(handoff_file(os.getcwd()))
        return
    if "--open" in sys.argv:
        print(open_items(os.getcwd()))
        return
    if "--grep" in sys.argv:
        i = sys.argv.index("--grep")
        term = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        print(grep(os.getcwd(), term) if term else "(usage: --grep <term>)")
        return
    if "--archive" in sys.argv:
        cwd = os.getcwd()
        active = handoff_file(cwd)
        outgoing = active.read_text(encoding="utf-8") if active.exists() else ""
        dest = archive_current(cwd)
        print(dest if dest else "(no non-empty handoff to archive)")
        if migrate_standing(cwd, outgoing):
            print(f"lifted '## Standing decisions' into {standing_file(cwd)} — it is injected at "
                  "boot from there now. Do NOT copy that section into the new handoff; edit that "
                  "file in place when a constraint changes.")
        note = standing_status(cwd)
        if note:
            print(note)
        return
    if "--history" in sys.argv:
        print(history(os.getcwd()))
        return
    if "--spawn" in sys.argv:
        print(spawn_session())
        return
    if "--check-context" in sys.argv:
        try:
            payload = json.load(sys.stdin)
        except Exception:
            payload = {}
        check_context(payload)
        return
    if "--context" in sys.argv:
        # manual read: newest transcript of this project (the current session)
        slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(os.getcwd()))
        d = pathlib.Path(os.path.expanduser("~")) / ".claude" / "projects" / slug
        files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime) if d.exists() else []
        b = breakeven(files[-1]) if files else None
        if not b:
            print("(no transcript usage found)")
            return
        print(f"context {b['ctx']} tokens | boot here ~{b['boot']} | {b['model']}\n"
              f"${b['usd_per_turn_saved']:.3f} wasted per further turn vs a fresh session\n"
              f"breakeven: /handoff + /clear wins if more than ~{b['turns']} turns of work remain")
        print(boot_breakdown(os.getcwd(), b))
        return
    # HOOK mode: cwd comes from the SessionStart payload on stdin (fallback to process cwd).
    cwd = os.getcwd()
    try:
        cwd = json.load(sys.stdin).get("cwd") or cwd
    except Exception:
        pass
    # Level 0 first, and independently of the handoff: constraints bind the session even when
    # there is nothing to resume (fresh project, or the handoff was cleared).
    st = standing_file(cwd)
    stxt = st.read_text(encoding="utf-8").strip() if st.exists() else ""
    if stxt:
        print(f"<!-- persistent, project-wide; outlives every session. Binding constraints, not "
              f"history. Overturned by what you do now? edit {st} and say so in this handoff. -->\n"
              f"{stxt}\n")
    f = handoff_file(cwd)
    if f.exists():
        txt = f.read_text(encoding="utf-8").strip()
        if txt:
            age = (datetime.datetime.now()
                   - datetime.datetime.fromtimestamp(f.stat().st_mtime)).days
            # age > 0 guard: a future mtime (clock skew, sync) must not print "-1 days ago"
            when = f"{age} days ago — verify against live state" if age > 0 else "by /handoff"
            print(f"# Resuming from saved handoff (written {when}). Continue from here:\n")
            # The `## Skills` names are already injected verbatim by session_inject.py; naming
            # them here only tells the agent to USE them, and to self-heal if one failed to resolve.
            skills = [ln.strip()[1:].strip() for ln in _section(txt, "Skills").splitlines()
                      if ln.strip().startswith(("-", "*"))]
            # `-name` = remove a machine default (session_inject.py), not a skill in play here.
            skills = [s for s in skills if s and not s.startswith(("<", "-"))]
            if skills:
                print("**FIRST ACTION, before anything else:** whatever the next user message is, "
                      "this work runs under: " + ", ".join(f"`{s}`" for s in skills) +
                      ". They are injected above — follow them from turn one. If any is missing "
                      "from your context, invoke the Skill tool for it before reading files, "
                      "running commands, or answering.\n")
            print(txt)


if __name__ == "__main__":
    main()
