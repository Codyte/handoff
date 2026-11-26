#!/usr/bin/env python3
"""Run one `/handoff workers agy` step: headless Antigravity CLI in its own git worktree.

agy only reads and edits files. Headless mode auto-denies commands, and we keep it that way:
the master runs the gate and commits. Never add --dangerously-skip-permissions.

    python agy_worker.py --repo <repo> --name <lane> --brief <file> [--timeout 600] [--model M] --paths <file|dir>...

--paths is a sparse checkout: only those files exist in the worktree, because everything agy
reads goes to Google. Never list secrets, keys or client data.

Exit 0: the worktree has changes to review. 1: agy failed or changed nothing. 2: usage.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RULES = ("\n\nRules: edit files only. Do not run commands, do not commit. Stay inside this "
         "directory. End with a report of 15 lines or fewer: what changed, what is not done.")


def find_agy():
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"
    return shutil.which("agy") or (str(local) if local.is_file() else None)


def verdict(returncode, output, changed):
    """agy exits 0 even when a permission was denied, so the exit code alone proves nothing."""
    if returncode != 0:
        return "FAIL: agy exit %s" % returncode
    if "jetski: no output produced" in output or not output.strip():
        return "FAIL: no answer (permission denied or empty output)"
    if not changed.strip():
        return "FAIL: no file changed"
    return "OK"


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


def selftest():
    assert verdict(0, "done", " M a.txt") == "OK"
    assert verdict(1, "done", " M a.txt").startswith("FAIL")
    assert verdict(0, "jetski: no output produced - denied", " M a.txt").startswith("FAIL")
    assert verdict(0, "", " M a.txt").startswith("FAIL")
    assert verdict(0, "done", "").startswith("FAIL")
    print("selftest ok")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # cp1252 console crashed on the report
    if "--selftest" in sys.argv:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--name", required=True, help="lane name; branch agy/<name>")
    ap.add_argument("--brief", required=True, help="UTF-8 file with the step brief")
    ap.add_argument("--timeout", type=int, default=600, help="seconds")
    ap.add_argument("--model", help="see `agy models`")
    ap.add_argument("--paths", nargs="+", required=True, help="the only tracked paths agy gets")
    a = ap.parse_args()

    agy = find_agy()
    if not agy:
        sys.exit("agy not found")
    repo = Path(a.repo).resolve()
    # outside the repo parent: a sibling of a skill repo would be discovered as a second skill
    tree = Path(tempfile.gettempdir()) / ("agy-%s-%s" % (repo.name, a.name))
    brief = Path(a.brief).read_text(encoding="utf-8")
    git(repo, "worktree", "add", "--no-checkout", "-b", "agy/" + a.name, str(tree))
    git(tree, "sparse-checkout", "set", "--no-cone", *("/" + x.replace("\\", "/") for x in a.paths))
    git(tree, "checkout")

    cmd = [agy, "-p", brief + RULES, "--mode", "accept-edits", "--add-dir", str(tree),
           "--print-timeout", "%ds" % a.timeout]
    if a.model:
        cmd += ["--model", a.model]
    try:
        p = subprocess.run(cmd, cwd=tree, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=a.timeout + 60)
        code, out = p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        code, out = 124, "timeout"

    changed = git(tree, "status", "--short")
    result = verdict(code, out, changed)
    print("\n".join(out.strip().splitlines()[-15:]))
    print("--- worktree: %s (branch agy/%s)" % (tree, a.name))
    print(changed.rstrip() or "(no changes)")
    print(result)
    sys.exit(0 if result == "OK" else 1)


if __name__ == "__main__":
    main()
