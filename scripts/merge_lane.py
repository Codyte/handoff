"""Close one offline lane of a workers run in one call (master side, from the main checkout).

    python merge_lane.py <branch> [--gate CMD] [--check CMD] [--tick STEP EVIDENCE] [--push] [--inspect] [--keep]

1. When main moved since the lane branched, rebase the branch inside its worktree and rerun --gate
   there (the lane's own offline gate). An unmoved base keeps the worker's gate result.
   A rebase stop whose conflicts are only `__navi__.md` maps or hunks inside NAV INDEX headers is
   regenerated (navindex) and continued; any other conflict stops with its paths named.
2. Print what changes: commits, `diff -w --numstat`, and deleted lines that are not NAV INDEX
   header churn (a proxied, condensed diff once made regenerated headers look like lost history).
3. `merge --ff-only`, then --check runs in the main checkout (the cheap acceptance gate).
4. Unlink every junction/symlink inside the worktree, THEN `worktree remove` and `branch -d`:
   a recursive delete that follows a junction wipes the main checkout's copy (e.g. `lib/`).
5. --tick closes the plan step (load_handoff.py --tick) and commits plan.md; --push pushes.

--keep skips step 4: the worker is being reused for a related step (workers.md § Reuse), so its
worktree, junctions and branch stay; after the ff merge the branch equals main.
--inspect stops after step 2. Any failure stops with exit 1 and names the step; nothing is forced.
Measured on tia F123 (2026-09-28): closing a lane by hand took the master ~4 calls at ~130k each.
"""
# ====================== BEGIN NAV INDEX ======================
# NAV INDEX — auto-generated symbol map (refresh via the navindex skill)
#   L45      60B  HEADER
#   L46      54B  NAV_MARK
#   L47      56B  CONFLICT
#   L48      81B  NAVINDEX
#   L51     288B  run
#   L58     359B  shell
#   L67     282B  worktree_of
#   L77     579B  links
#   L98     222B  unlink
#   L104    874B  nav_only
#   L126    881B  regenerate
#   L145    1.4K  rebase
#   L169    2.6K  main
#   L238    1.9K  _selftest
#   L280    2.8K  _selftest_nav
# ======================= END NAV INDEX =======================

import os
import re
import subprocess
import sys

HEADER = re.compile(r"NAV INDEX|^-\s*(<!--|//|#)\s+L\d+\s")
NAV_MARK = re.compile(r"=+ (BEGIN|END) NAV INDEX =+")
CONFLICT = re.compile(r"^(<{7}|={7}|\|{7}|>{7})(\s|$)")
NAVINDEX = os.path.expanduser("~/.claude/skills/navindex/scripts/navindex.py")


def run(args, cwd=None, check=True):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode:
        sys.exit(f"FAIL {' '.join(args)}\n{(p.stdout + p.stderr).strip()[-1500:]}")
    return p.stdout.strip()


def shell(cmd, cwd, label):
    p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    tail = "\n".join((p.stdout + p.stderr).strip().splitlines()[-15:])
    print(f"--- {label} (exit {p.returncode})\n{tail}")
    if p.returncode:
        sys.exit(f"FAIL {label}: {cmd}")


def worktree_of(branch):
    path = None
    for line in run(["git", "worktree", "list", "--porcelain"]).splitlines():
        if line.startswith("worktree "):
            path = line[9:]
        elif line == f"branch refs/heads/{branch}":
            return path
    return None


def links(root, depth=3):
    """Junctions and symlinks inside the worktree, never descending into them."""
    found = []

    def walk(d, n):
        try:
            entries = list(os.scandir(d))
        except OSError:
            return
        for e in entries:
            if e.name == ".git":
                continue
            if e.is_symlink() or (hasattr(e, "is_junction") and e.is_junction()):
                found.append(e.path)
            elif n and e.is_dir(follow_symlinks=False):
                walk(e.path, n - 1)

    walk(root, depth)
    return found


def unlink(path):
    # rmdir on a junction or directory symlink removes the link only, and refuses a real
    # non-empty directory instead of deleting it.
    os.rmdir(path) if os.path.isdir(path) else os.unlink(path)


def nav_only(path):
    """True when the conflict in `path` is generated text only: a `__navi__.md` map, or a file whose
    every conflict marker lies inside its (first) NAV INDEX block. A content hunk outside the
    markers is never auto-resolved: a hand "keep main's hunk" once silently dropped a doc row."""
    if os.path.basename(path) == "__navi__.md":
        return True
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return False
    state, seen = 0, False                  # 0 before the block, 1 inside, 2 after
    for line in lines:
        m = NAV_MARK.search(line)
        if m and state == (0 if m.group(1) == "BEGIN" else 1):
            state += 1
        elif CONFLICT.match(line):
            if state != 1:
                return False
            seen = True
    return seen


def regenerate(wt, path):
    """Resolve one NAV-only conflict: keep the first side of each hunk (the clean merge around it
    stays), then rebuild the header (file) or the map (its folder) with navindex."""
    if os.path.basename(path) == "__navi__.md":
        target, extra = os.path.dirname(path) or ".", ["--map-only"]
    else:
        full, out, skip = os.path.join(wt, path), [], False
        with open(full, encoding="utf-8", errors="surrogateescape", newline="") as f:
            for line in f:
                if CONFLICT.match(line):
                    skip = line[0] in "|="
                elif not skip:
                    out.append(line)
        with open(full, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.write("".join(out))
        target, extra = path, []
    run([sys.executable, NAVINDEX, target, *extra], cwd=wt)


def rebase(into, wt):
    """Rebase the branch checked out in `wt` onto `into`, regenerating NAV-only conflicts; any other
    conflict exits naming its paths, the rebase left stopped in `wt` for the master to resolve."""
    env = dict(os.environ, GIT_EDITOR="true")
    git = lambda *a: subprocess.run(["git", *a], cwd=wt, env=env, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace")
    p = git("rebase", into)
    while p.returncode:
        paths = run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=wt).splitlines()
        content = [f for f in paths if not nav_only(os.path.join(wt, f))]
        if not paths or content:
            sys.exit(f"FAIL rebase onto {into} stopped in {wt}; conflicted outside NAV INDEX: "
                     f"{', '.join(content) or '(none)'}; resolve there or `git rebase --abort`\n"
                     + (p.stdout + p.stderr).strip()[-800:])
        for f in paths:
            regenerate(wt, f)
        run(["git", "add", "-A", "--", *paths], cwd=wt)
        side = run(["git", "diff", "--name-only"], cwd=wt).splitlines()
        if side:                            # navindex touched another map: keep the commit's own
            run(["git", "checkout", "--", *side], cwd=wt)
        print(f"regenerated NAV-only conflict: {', '.join(paths)}")
        p = git("rebase", "--continue")


def main(argv):
    if not argv or argv[0].startswith("-"):
        sys.exit(__doc__)
    branch, opts = argv[0], argv[1:]

    def opt(name, n=1):
        if name not in opts:
            return None
        i = opts.index(name)
        vals = opts[i + 1:i + 1 + n]
        if len(vals) < n:
            sys.exit(f"{name} needs {n} value(s)")
        return vals if n > 1 else vals[0]

    into = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    wt = worktree_of(branch)
    if not wt:
        sys.exit(f"FAIL no worktree has branch {branch}")
    print(f"=== 1 base ({branch} -> {into}) ===")
    if subprocess.run(["git", "merge-base", "--is-ancestor", into, branch]).returncode:
        rebase(into, wt)
        print(f"rebased onto {into}")
        if opt("--gate"):
            shell(opt("--gate"), wt, "lane gate after rebase")
    else:
        print("base ok, no rebase")

    print("=== 2 changes ===")
    print(run(["git", "log", "--oneline", f"{into}..{branch}"]) or "(no commits)")
    print(run(["git", "diff", "-w", "--numstat", f"{into}..{branch}"]))
    removed = [line for line in run(["git", "diff", "-w", f"{into}..{branch}"]).splitlines()
               if line.startswith("-") and not line.startswith("---") and not HEADER.search(line)]
    print(f"deleted non-header lines: {len(removed)}")
    for line in removed[:12]:
        print("  " + line[:150])
    if "--inspect" in opts:
        return

    print("=== 3 merge ===")
    print((run(["git", "merge", "--ff-only", branch]).splitlines() or [""])[-1])
    if opt("--check"):
        shell(opt("--check"), None, "check in main checkout")

    print("=== 4 cleanup ===")
    if "--keep" in opts:                    # worker reused for a related step: its branch now equals main
        print(f"kept worktree {wt} and branch {branch} (--keep)")
    for p in ([] if "--keep" in opts else links(wt)):
        unlink(p)
        print(f"unlinked {p}")
    if "--keep" not in opts:
        run(["git", "worktree", "remove", wt])
        run(["git", "branch", "-d", branch])
        print(f"removed worktree {wt} and branch {branch}")

    tick = opt("--tick", 2)
    if tick:
        print("=== 5 tick ===")
        loader = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "load_handoff.py")
        out = run([sys.executable, loader, "--tick"] + tick)
        print(out)
        if out.startswith("ticked"):
            plan = run([sys.executable, loader, "--plan-path"])
            run(["git", "add", plan])
            run(["git", "commit", "-q", "-m", f"plan: step {tick[0]} ticked ({branch})"])
    if "--push" in opts:
        run(["git", "push", "-q"])
        print("pushed")


def _selftest():
    """Temp repo + lane worktree + a junction/symlink to the main checkout's folder: the merge must
    land, and the linked folder's file must survive the worktree removal."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        main_dir = os.path.join(td, "main")
        os.makedirs(os.path.join(main_dir, "lib"))
        open(os.path.join(main_dir, "lib", "keep.txt"), "w").write("x")
        g = lambda *a, cwd=main_dir: run(["git", *a], cwd=cwd)
        g("init", "-q", "-b", "main")
        g("config", "user.email", "t@t")
        g("config", "user.name", "t")
        open(os.path.join(main_dir, ".gitignore"), "w").write("lib/\n")
        g("add", ".gitignore")
        g("commit", "-q", "-m", "base")
        wt = os.path.join(td, "lane")
        g("worktree", "add", "-q", "-b", "lane1", wt)
        open(os.path.join(wt, "a.txt"), "w").write("a\n")
        g("add", "a.txt", cwd=wt)
        g("commit", "-q", "-m", "lane work", cwd=wt)
        open(os.path.join(main_dir, "b.txt"), "w").write("b\n")     # main moved: rebase path
        g("add", "b.txt")
        g("commit", "-q", "-m", "main moved")
        target, link = os.path.join(main_dir, "lib"), os.path.join(wt, "lib")
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True, check=True)
        else:
            os.symlink(target, link)
        cwd = os.getcwd()
        os.chdir(main_dir)
        try:
            main(["lane1"])
        finally:
            os.chdir(cwd)
        assert os.path.exists(os.path.join(main_dir, "a.txt")), "merge did not land"
        assert "main moved" in run(["git", "log", "--oneline", "-3"], cwd=main_dir), "rebase lost main"
        assert os.path.exists(os.path.join(target, "keep.txt")), "junction target was wiped"
        assert not os.path.exists(wt), "worktree not removed"
    _selftest_nav()
    print("selftest ok")


def _selftest_nav():
    """Scratch repo: a rebase whose conflicts are only a NAV INDEX header and a `__navi__.md` map
    lands with both sides' content and current navigation; a content conflict still stops, named."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        g = lambda *a: run(["git", *a], cwd=d)
        nav = lambda *a: run([sys.executable, NAVINDEX, *a], cwd=d)

        def write(rel, text):
            os.makedirs(os.path.join(d, os.path.dirname(rel) or "."), exist_ok=True)
            open(os.path.join(d, rel), "w", newline="\n").write(text)

        def commit(msg, *paths):
            g("add", *paths)
            g("commit", "-q", "-m", msg)

        def doc(a="", b="", c="three"):     # a/b insert 3 and 4 lines: the headers really diverge
            write("doc.md", f"# Doc\n\n## One\none\n{a}\n## Two\ntwo\n{b}\n## Three\n{c}\n")
            nav("doc.md")

        g("init", "-q", "-b", "main")
        for k, v in (("user.email", "t@t"), ("user.name", "t"), ("core.autocrlf", "false")):
            g("config", k, v)
        write(".gitignore", ".navindex-cache.json\n")
        write("pkg/a.py", "def a():\n    pass\n")
        doc()
        nav("pkg")
        commit("base", ".gitignore", "doc.md", "pkg")
        g("branch", "lane1")
        g("branch", "lane2")
        main_a = "\n## Main\nmain\n"
        doc(a=main_a)
        write("pkg/c.py", "def c():\n    pass\n")
        nav("pkg")
        commit("main moved", "doc.md", "pkg")
        doc(a=main_a, c="three-main")
        commit("main edits three", "doc.md")

        g("checkout", "-q", "lane1")        # (1) header + map conflicts only: regenerated, lands
        doc(b="\n## Lane\nlane\nlane2\n")
        write("pkg/b.py", "def b():\n    pass\n")
        nav("pkg")
        commit("lane1", "doc.md", "pkg")
        rebase("main", d)
        text = open(os.path.join(d, "doc.md")).read()
        assert all(s in text for s in ("BEGIN NAV INDEX", "## Main", "## Lane", "three-main")), \
            "a side's content or the header was lost"
        assert "b.py" in open(os.path.join(d, "pkg", "__navi__.md")).read(), "map lost the lane file"
        nav("doc.md")
        nav("pkg", "--map-only")
        assert not g("status", "--porcelain"), "navigation not current: " + g("status", "--porcelain")

        g("checkout", "-q", "lane2")        # (2) content conflict on `three`: must stop, named
        doc(c="three-lane")
        commit("lane2", "doc.md")
        try:
            rebase("main", d)
            raise AssertionError("content conflict did not stop")
        except SystemExit as e:
            assert "doc.md" in str(e), f"conflicted path not named: {e}"
        g("rebase", "--abort")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _selftest() if "--selftest" in sys.argv else main(sys.argv[1:])
