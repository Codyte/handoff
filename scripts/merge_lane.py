"""Close one offline lane of an orchestrate run in one call (master side, from the main checkout).

    python merge_lane.py <branch> [--gate CMD] [--check CMD] [--tick STEP EVIDENCE] [--push] [--inspect]

1. When main moved since the lane branched, rebase the branch inside its worktree and rerun --gate
   there (the lane's own offline gate). An unmoved base keeps the worker's gate result.
2. Print what changes: commits, `diff -w --numstat`, and deleted lines that are not NAV INDEX
   header churn (a proxied, condensed diff once made regenerated headers look like lost history).
3. `merge --ff-only`, then --check runs in the main checkout (the cheap acceptance gate).
4. Unlink every junction/symlink inside the worktree, THEN `worktree remove` and `branch -d`:
   a recursive delete that follows a junction wipes the main checkout's copy (e.g. `lib/`).
5. --tick closes the plan step (load_handoff.py --tick) and commits plan.md; --push pushes.

--inspect stops after step 2. Any failure stops with exit 1 and names the step; nothing is forced.
Measured on tia F123 (2026-09-28): closing a lane by hand took the master ~4 calls at ~130k each.
"""
import os
import re
import subprocess
import sys

HEADER = re.compile(r"NAV INDEX|^-\s*(<!--|//|#)\s+L\d+\s")


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
        run(["git", "rebase", into], cwd=wt)
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
    for p in links(wt):
        unlink(p)
        print(f"unlinked {p}")
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
    print("selftest ok")


if __name__ == "__main__":
    _selftest() if "--selftest" in sys.argv else main(sys.argv[1:])
