"""Token profile of Claude Code sessions and their subagents, from the transcripts.

    python scripts/session_stats.py <project-transcript-dir> [--last N | <session-id> ...]

Per session: requests, boot (first request's context), mean and peak context per request, total
tokens processed (what every round-trip re-read), output tokens. Subagents (workers) are listed
under their session, then a total. The number that decides whether orchestration paid off is
`processed` of master + workers against a single-session baseline doing the same kind of work.
"""
import glob
import json
import os
import sys


def profile(path):
    seen, ctxs, out, model = set(), [], 0, None
    for line in open(path, encoding="utf-8"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "assistant":
            continue
        m = e.get("message") or {}
        rid = e.get("requestId") or m.get("id")
        if rid in seen:
            continue                    # one request is logged once per content block
        seen.add(rid)
        u = m.get("usage") or {}
        ctx = (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
               + u.get("cache_creation_input_tokens", 0))
        if ctx == 0:
            continue                    # synthetic entries carry no usage
        ctxs.append(ctx)
        out += u.get("output_tokens", 0)
        model = m.get("model") or model
    if not ctxs:
        return None
    return {"model": model, "reqs": len(ctxs), "boot": ctxs[0], "mean": sum(ctxs) // len(ctxs),
            "peak": max(ctxs), "processed": sum(ctxs), "out": out}


def row(label, p):
    return ("%-26s %-18s reqs=%4d boot=%6d mean=%7d peak=%7d processed=%11d out=%7d"
            % (label[:26], (p["model"] or "?")[:18], p["reqs"], p["boot"], p["mean"], p["peak"],
               p["processed"], p["out"]))


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    root, rest = argv[0], argv[1:]
    mains = sorted(glob.glob(os.path.join(root, "*.jsonl")), key=os.path.getmtime)
    if rest and rest[0] == "--last":
        mains = mains[-int(rest[1]):]
    elif rest:
        mains = [os.path.join(root, s + ".jsonl") for s in rest]
    for f in mains:
        sid = os.path.basename(f)[:-6]
        m = profile(f)
        if not m:
            continue
        print(row("session " + sid[:8], m))
        total = m["processed"]
        for w in sorted(glob.glob(os.path.join(root, sid, "subagents", "*.jsonl")), key=os.path.getmtime):
            p = profile(w)
            if p:
                print("  " + row(os.path.basename(w)[:-6], p))
                total += p["processed"]
        print("  total processed (master + workers): %d" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
