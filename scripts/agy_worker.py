#!/usr/bin/env python3
"""One `/handoff workers` step on the Antigravity CLI: agy edits, this script gates and commits.

agy gets file tools only (headless auto-denies commands and reads outside the workspace; keep it
that way, never add --dangerously-skip-permissions). Everything else a worker does happens here:
isolated worktree, gate, retry with the gate error, commit, short report.

    python agy_worker.py --repo <repo> --name <lane> --brief <file> --gate "<command>"
                         [--message "<subject>"] [--retries 2] [--timeout 900] [--model M]
    python agy_worker.py ... --name <same lane> --brief <next>   # reuses worktree and conversation

<repo>/.agyignore is required: gitignore-style patterns of files that never enter the worktree,
because everything agy reads goes to Google. An empty file means "all tracked files may go".

Exit 0 = DONE (gate passed, committed). 1 = PARTIAL or FAILED. Merge with merge_lane.py.
The gate runs agy-written code on this machine: read the diff before running anything riskier.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ALWAYS_EXCLUDED = [".license/", ".handoff/", ".env", ".env.*", "*.pem", "*.pfx", "*.key", "*private*.xml"]
RULES = """

Rules (you are a worker; a master reads only your final answer):
- Do only this step. Anything out of scope goes under `open:`.
- Read AGENTS.md / CLAUDE.md in this folder if present and obey them.
- Edit files only. You cannot run commands or commit; the caller runs the gate and commits.
- Commands, workflows and subagents are denied and calling one can end your turn with nothing
  done. Use only the file read, search and write tools.
- Stay inside this folder. Read narrowly; never rewrite a whole file for a small change.
- If the choice is irreversible or the task looks wrong, change nothing and say NEEDS_DECISION.
- Final answer, 8 lines max: `changed:`, `rulings:` (decision and why), `open:`."""
MIN_QUOTA = 5  # percent
FALLBACK_MODEL = "gemini-4-neon-high"  # separate quota from the Claude/GPT group


def find_agy():
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"
    return shutil.which("agy") or (str(local) if local.is_file() else None)


def run(cmd, cwd=None, timeout=None, shell=False):
    try:
        p = subprocess.run(cmd, cwd=cwd, shell=shell, timeout=timeout, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def git(cwd, *args):
    code, out, err = run(["git", "-C", str(cwd), *args])
    if code:
        sys.exit("git %s: %s" % (" ".join(args[:3]), err.strip()[:400]))
    return out


def call_agy(agy, tree, prompt, conversation, timeout, model):
    cmd = [agy, "-p", prompt, "--mode", "accept-edits", "--add-dir", str(tree),
           "--output-format", "json", "--print-timeout", "%ds" % timeout]
    if conversation:
        cmd += ["--conversation", conversation]
    if model:
        cmd += ["--model", model]
    code, out, err = run(cmd, cwd=tree, timeout=timeout + 60)
    try:
        data = json.JSONDecoder().raw_decode(out.strip())[0]
    except ValueError:
        data = {"status": "NO_JSON", "response": (out + err)[-1500:]}
    data.setdefault("exit", code)
    return data


def quota_low(agy):
    """Lowest remaining percent per model group, from `agy -p /usage`; None when unreadable."""
    _, out, _ = run([agy, "-p", "/usage", "--print-timeout", "60s"], cwd=tempfile.gettempdir(), timeout=90)
    low = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2].strip().endswith("%"):
            pct = float(parts[2].strip()[:-1])
            low[parts[0]] = min(pct, low.get(parts[0], 100.0))
    return low or None


def excludes(repo):
    f = repo / ".agyignore"
    if not f.is_file():
        sys.exit("refused: %s is missing (list what must never go to Google; empty = nothing extra)" % f)
    lines = [l.strip() for l in f.read_text(encoding="utf-8").splitlines()]
    return ALWAYS_EXCLUDED + [l for l in lines if l and not l.startswith(("#", "!"))]


def changed_paths(tree):
    out = git(tree, "status", "--porcelain", "-z", "--untracked-files=all", "--no-renames")
    return [e[3:] for e in out.split("\0") if e]


def work(repo, tree, name, brief, gate, message, retries, agent, state):
    """agent(prompt, conversation) -> agy JSON. Returns the report dict."""
    if not tree.exists():
        patterns = ["/*"] + ["!" + p for p in excludes(repo)]
        git(repo, "worktree", "add", "--no-checkout", "-b", "agy/" + name, str(tree))
        git(tree, "sparse-checkout", "set", "--no-cone", *patterns)
        git(tree, "checkout")
    unlink_junctions(tree)
    report = {"status": "FAILED", "commit": None, "gate": None, "files": [], "attempts": 0,
              "tokens": 0, "denied": [], "answer": "", "log": []}
    prompt = brief + RULES
    for attempt in range(retries + 1):
        data = agent(prompt, state.get("conversation"))
        report["log"].append(data)
        report["attempts"] = attempt + 1
        state["conversation"] = data.get("conversation_id") or state.get("conversation")
        report["tokens"] += (data.get("usage") or {}).get("total_tokens", 0)
        report["denied"] += [d.get("action", "?") for d in data.get("denied_actions") or []]
        report["answer"] = data.get("response") or ""
        # captured before the gate, so build output the gate leaves behind is never committed
        report["files"] = changed_paths(tree)
        ok = data.get("status") == "SUCCESS" and not data.get("exit")
        failure = "agy %s, exit %s: %s" % (data.get("status"), data.get("exit"), str(data.get("error", ""))[:200])
        if not report["files"]:
            report["error"] = "no file changed" if ok else failure
            if ok and data.get("denied_actions") and attempt < retries:
                prompt = ("A denied tool call ended your turn with no change. Use only the file read, "
                          "search and write tools.\n\n" + brief + RULES)
                continue
            return report
        if not ok:  # agy died after editing: the gate still decides, the master is told
            report["warn"] = failure
        code, out, err = run(gate, cwd=tree, shell=True, timeout=1800)
        report["gate"] = code
        if code == 0:
            git(tree, "add", "-A", "--", *report["files"])
            git(tree, "commit", "-q", "-m", message)
            report.update(status="DONE", commit=git(tree, "rev-parse", "--short", "HEAD").strip())
            report.pop("error", None)
            return report
        tail = (out + "\n" + err).strip()[-3000:]
        report.update(status="PARTIAL", error="gate exit %s: %s" % (code, tail[-300:]))
        if not ok:
            return report
        prompt = "The gate command `%s` failed (exit %s). Fix the cause. Output tail:\n%s" % (gate, code, tail)
    return report


def unlink_junctions(tree):
    """Drop links (e.g. a gate's lib/) left at the worktree root; a recursive delete follows them."""
    if not tree.is_dir():
        return
    for entry in os.scandir(tree):
        if getattr(os.path, "isjunction", lambda p: False)(entry.path):
            os.rmdir(entry.path)  # removes the link only


def with_fallback(call, models, brief, notes):
    """call(prompt, conversation, model); moves to the next model when a quota runs out."""
    def agent(prompt, conversation):
        data = call(prompt, conversation, models[0])
        if "quota reached" in str(data.get("error", "")).lower() and len(models) > 1:
            notes.append("quota reached on %s, switched to %s" % (models[0], models[1]))
            models.pop(0)
            data = call(prompt if brief in prompt else brief + RULES + "\n\n" + prompt, None, models[0])
        return data
    return agent


def selftest():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.name", "t")
        git(repo, "config", "user.email", "t@t")
        for rel in ("a.txt", ".license/private.xml", "client/x.txt"):
            (repo / rel).parent.mkdir(exist_ok=True)
            (repo / rel).write_text("one\n")
        (repo / ".agyignore").write_text("client/\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "init")
        gate = '"%s" -c "import sys; sys.exit(0 if \'good\' in open(\'a.txt\').read() else 1)"' % sys.executable

        def case(name, texts, retries=2):
            tree, seq = Path(tmp) / name, list(texts)

            def agent(prompt, conversation):
                text = seq.pop(0)
                if text:
                    (tree / "a.txt").write_text(text)
                return {"status": "SUCCESS", "conversation_id": "c1", "response": "ok", "exit": 0}

            r = work(repo, tree, name, "brief", gate, "msg " + name, retries, agent, {})
            assert not (tree / ".license").exists() and not (tree / "client").exists(), "excluded file leaked"
            return r

        assert case("pass", ["good\n"])["status"] == "DONE"
        fixed = case("fix", ["bad\n", "good\n"])
        assert fixed["status"] == "DONE" and fixed["attempts"] == 2
        gave = case("giveup", ["bad\n", "bad2\n"], retries=1)
        assert gave["status"] == "PARTIAL" and gave["commit"] is None
        assert case("nochange", [""])["status"] == "FAILED"

        def scripted(name, steps):
            tree, seq = Path(tmp) / name, list(steps)

            def agent(prompt, conversation):
                text, extra = seq.pop(0)
                if text:
                    (tree / "a.txt").write_text(text)
                return dict({"status": "SUCCESS", "response": "ok", "exit": 0}, **extra)

            return work(repo, tree, name, "brief", gate, "msg " + name, 2, agent, {})

        denied = scripted("denied", [("", {"denied_actions": [{"action": "command"}]}), ("good\n", {})])
        assert denied["status"] == "DONE" and denied["attempts"] == 2
        died = scripted("died", [("good\n", {"status": "ERROR", "exit": 3, "error": "boom"})])
        assert died["status"] == "DONE" and "boom" in died["warn"]
        seen, notes = [], []

        def call(prompt, conversation, model):
            seen.append(model)
            return {"error": "Third-party quota reached."} if model == "claude-x" else {"status": "SUCCESS"}

        assert with_fallback(call, ["claude-x", "gem"], "b", notes)("b", "c1")["status"] == "SUCCESS"
        assert seen == ["claude-x", "gem"] and notes
        if os.name == "nt":
            target, holder = Path(tmp) / "target", Path(tmp) / "holder"
            target.mkdir()
            holder.mkdir()
            (target / "keep.txt").write_text("x")
            assert run(["cmd", "/c", "mklink", "/J", str(holder / "lib"), str(target)])[0] == 0
            unlink_junctions(holder)
            assert not (holder / "lib").exists() and (target / "keep.txt").exists()
        (repo / ".agyignore").unlink()
        try:
            case("noignore", ["good\n"])
            raise AssertionError("ran without .agyignore")
        except SystemExit as e:
            assert "refused" in str(e)
    print("selftest ok")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--selftest" in sys.argv:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--name", required=True, help="lane name; branch agy/<name>; same name = warm reuse")
    ap.add_argument("--brief", required=True, help="UTF-8 file with the step brief")
    ap.add_argument("--gate", required=True, help="shell command run in the worktree; exit 0 = done")
    ap.add_argument("--message", help="commit subject")
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=900, help="seconds per agy call")
    ap.add_argument("--model", help="see `agy models`")
    a = ap.parse_args()

    agy = find_agy()
    if not agy:
        sys.exit("agy not found")
    low = quota_low(agy)

    def group_of(model):
        return "Claude and GPT models" if model and model.startswith(("claude", "gpt")) else "Gemini Models"

    models, notes = [a.model], []
    if group_of(a.model) != "Gemini Models":
        models.append(FALLBACK_MODEL)
    while models and low and low.get(group_of(models[0]), 100) < MIN_QUOTA:
        notes.append("quota below %s%% for %s" % (MIN_QUOTA, models.pop(0)))
    if not models:
        sys.exit("STATUS: FAILED\nagy quota below %s%%; use the Claude worker" % MIN_QUOTA)
    group = group_of(models[0])
    repo = Path(a.repo).resolve()
    # outside the repo parent: a sibling of a skill repo would be discovered as a second skill
    tree = Path(tempfile.gettempdir()) / ("agy-%s-%s" % (repo.name, a.name))
    state_file = tree.with_name(tree.name + ".state.json")
    state = json.loads(state_file.read_text()) if tree.exists() and state_file.exists() else {}
    brief = Path(a.brief).read_text(encoding="utf-8")
    agent = with_fallback(lambda p, c, m: call_agy(agy, tree, p, c, a.timeout, m), models, brief, notes)
    try:
        r = work(repo, tree, a.name, brief, a.gate, a.message or "agy: " + a.name, a.retries, agent, state)
    finally:
        unlink_junctions(tree)  # also after an interrupted gate
    state_file.write_text(json.dumps(state))
    log = tree.with_name(tree.name + ".log.json")
    log.write_text(json.dumps(r["log"], indent=1), encoding="utf-8")

    print("STATUS: " + r["status"])
    print("commits: %s" % (r["commit"] or "none"))
    print("gate: %s -> exit %s (attempts %s)" % (a.gate, r["gate"], r["attempts"]))
    print("files: " + (", ".join(r["files"][:12]) or "none") + (" ..." if len(r["files"]) > 12 else ""))
    if r.get("error"):
        print("error: " + " ".join(r["error"].split())[:400])
    for note in notes + ([r["warn"]] if r.get("warn") else []):
        print("warn: " + " ".join(note.split())[:300])
    if r["denied"]:
        print("denied: " + ", ".join(sorted(set(r["denied"]))))
    for line in r["answer"].strip().splitlines()[:8]:
        print("agy> " + line[:200])
    print("worktree: %s (branch agy/%s) tokens: %s quota-left: %s log: %s"
          % (tree, a.name, r["tokens"], low.get(group) if low else "?", log))
    sys.exit(0 if r["status"] == "DONE" else 1)


if __name__ == "__main__":
    main()
