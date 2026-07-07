#!/usr/bin/env python3
"""Handoff loader/locator — shared by the /handoff skill and the SessionStart hook.

Two modes:
  python load_handoff.py --path     -> print the handoff file path for the current project (the
                                       /handoff skill writes there, so skill and hook always agree)
  python load_handoff.py            -> HOOK mode: read the SessionStart JSON on stdin, and if a
                                       handoff exists for that project, print it. A SessionStart
                                       hook's stdout is injected as context, so the next session
                                       (after /clear) resumes from the saved state automatically.

Handoff files live under ~/.claude/handoff/<sanitized-project-path>.md — per machine, NOT in the
skills repo, so session state never pollutes the versioned skills.
"""
# ====================== BEGIN NAV INDEX ======================
# NAV INDEX — auto-generated symbol map (refresh via the navindex skill)
#   L41    _key
#   L45    _git_root
#   L55    handoff_file
#   L67    _archive_dir
#   L74    _archive_files
#   L81    ensure_hook
#   L106   archive_current
#   L124   _section
#   L131   history
#   L151   open_items
#   L161   grep
#   L173   _selftest
#   L185   main
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


def ensure_hook():
    """Idempotently register the SessionStart hook that injects the active handoff at boot.
    The skill (writer) and this hook (reader) are separate pieces; copying the skill folder to a
    new machine does NOT bring the hook. Running this once on a machine wires it, so the *next*
    session there auto-loads handoffs. Writes THIS file's absolute path → each machine self-
    registers a command valid for its own home dir (no hardcoded username)."""
    settings = pathlib.Path(os.path.expanduser("~")) / ".claude" / "settings.json"
    cmd = f'python "{os.path.abspath(__file__)}"'
    data = {}
    if settings.exists():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except Exception:
            print("settings.json present but unreadable — left untouched; add the hook by hand")
            return
    ss = data.setdefault("hooks", {}).setdefault("SessionStart", [])
    if "load_handoff.py" in json.dumps(ss):   # match by filename → survives a moved home dir
        print("SessionStart hook already present — nothing to do")
        return
    ss.append({"hooks": [{"type": "command", "command": cmd}]})
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"registered SessionStart hook -> {cmd}")


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
    arc_dir = _archive_dir(cwd)
    arc_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")
    dest = arc_dir / (stamp + ".md")
    dest.write_text(txt + "\n", encoding="utf-8")
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
    f = handoff_file(cwd)
    txt = f.read_text(encoding="utf-8") if f.exists() else ""
    parts = [f"**{h}:**\n{b}" for h in ("Next steps", "Open / blockers")
             if (b := _section(txt, h))]
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
    print("selftest ok")


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
        dest = archive_current(os.getcwd())
        print(dest if dest else "(no non-empty handoff to archive)")
        return
    if "--history" in sys.argv:
        print(history(os.getcwd()))
        return
    # HOOK mode: cwd comes from the SessionStart payload on stdin (fallback to process cwd).
    cwd = os.getcwd()
    try:
        cwd = json.load(sys.stdin).get("cwd") or cwd
    except Exception:
        pass
    f = handoff_file(cwd)
    if f.exists():
        txt = f.read_text(encoding="utf-8").strip()
        if txt:
            print("# Resuming from saved handoff (written by /handoff). Continue from here:\n")
            print(txt)


if __name__ == "__main__":
    main()
