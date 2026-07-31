#!/usr/bin/env python3
"""Cluster splunkd.log messages into patterns and summarize crash logs.

Raw error lines are useless at diag scale — one bad regex produces 40,000
identical WARNs. This normalizes variable parts out of each message so
repetitions collapse into a single row carrying a count and a first/last
timestamp. Volume and time distribution are what identify an incident.

Usage:
    python3 log_triage.py --diag <path> [--level WARN] [--top 25]
                          [--component TcpOutputProc] [--grep 'text']
                          [--since '06-15-2024 00:00:00'] [--json]
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict

LINE = re.compile(
    r"^(?P<ts>\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})\.\d+\s+"
    r"(?P<tz>[+-]\d{4})?\s*"
    r"(?P<level>DEBUG|INFO|WARN|ERROR|FATAL|CRIT)\s+"
    r"(?P<component>[\w:.\-]+)\s*"
    r"(?:\[[^\]]*\])?\s*-?\s*"
    r"(?P<msg>.*)$"
)

LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3, "CRIT": 4, "FATAL": 5}

# Order matters: strip the most specific things first.
NORMALIZERS = [
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<GUID>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"), "<IP>"),
    (re.compile(r"(?<=[=\s])/[\w./\-]{4,}"), "<PATH>"),
    (re.compile(r'"[^"]*"'), '"<STR>"'),
    (re.compile(r"'[^']*'"), "'<STR>'"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (re.compile(r"\b\d[\d,.]*\b"), "<N>"),
    (re.compile(r"\s+"), " "),
]


def normalize(msg):
    out = msg
    for pat, repl in NORMALIZERS:
        out = pat.sub(repl, out)
    return out.strip()[:300]


def log_files(diag):
    """splunkd.log plus its rotations, oldest first so timestamps stay ordered."""
    base = os.path.join(diag, "log", "splunkd.log")
    rotated = sorted(
        glob.glob(base + ".*"),
        key=lambda p: int(re.sub(r"\D", "", os.path.basename(p)) or 0),
        reverse=True,
    )
    return [p for p in rotated + [base] if os.path.exists(p)]


def triage(diag, min_level="WARN", component=None, grep=None, since=None):
    floor = LEVEL_RANK.get(min_level.upper(), 2)
    patterns = defaultdict(lambda: {"count": 0, "first": None, "last": None, "sample": None})
    unparsed = scanned = 0
    grep_re = re.compile(grep, re.I) if grep else None

    for path in log_files(diag):
        try:
            fh = open(path, "r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                scanned += 1
                m = LINE.match(line)
                if not m:
                    unparsed += 1
                    continue
                lvl = m.group("level")
                if LEVEL_RANK.get(lvl, 0) < floor:
                    continue
                comp = m.group("component")
                if component and component.lower() not in comp.lower():
                    continue
                msg = m.group("msg")
                if grep_re and not grep_re.search(msg) and not grep_re.search(comp):
                    continue
                ts = m.group("ts")
                if since and ts < since:
                    continue
                key = (lvl, comp, normalize(msg))
                e = patterns[key]
                e["count"] += 1
                e["last"] = ts
                if e["first"] is None:
                    e["first"] = ts
                    e["sample"] = msg.strip()[:400]

    rows = [
        {"level": k[0], "component": k[1], "pattern": k[2], **v}
        for k, v in patterns.items()
    ]
    rows.sort(key=lambda r: (-LEVEL_RANK.get(r["level"], 0), -r["count"]))
    return {"findings": rows, "lines_scanned": scanned, "lines_unparsed": unparsed}


CRASH_SIGNAL = re.compile(r"Received fatal signal (\d+)|signal (\d+)", re.I)


def crashes(diag):
    """Crash logs are short and always worth reading in full — summarize each."""
    out = []
    for path in sorted(glob.glob(os.path.join(diag, "log", "crash-*.log"))):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read(20000)
        except OSError:
            continue
        sig = CRASH_SIGNAL.search(text)
        ver = re.search(r"Splunk\s+([\d.]+)\s+\(build\s+([\w.]+)\)", text)
        threads = re.search(r"Threads running:\s*(\d+)", text)
        crashing = re.search(r"Crashing thread:\s*(\S+)", text)
        frames = [
            ln.strip()[:160]
            for ln in text.splitlines()
            if re.match(r"^\s*\[0x[0-9a-fA-F]+\]", ln)
        ][:8]
        out.append({
            "file": os.path.basename(path),
            "signal": (sig.group(1) or sig.group(2)) if sig else None,
            "version": f"{ver.group(1)} build {ver.group(2)}" if ver else None,
            "crashing_thread": crashing.group(1) if crashing else None,
            "threads_running": threads.group(1) if threads else None,
            "top_frames": frames,
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diag", required=True)
    ap.add_argument("--level", default="WARN", help="minimum level (default WARN)")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--component", help="filter to a component substring")
    ap.add_argument("--grep", help="regex filter on message text")
    ap.add_argument("--since", help="'MM-DD-YYYY HH:MM:SS' lower bound")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(args.diag):
        print(f"Not a directory: {args.diag}", file=sys.stderr)
        return 1

    result = triage(args.diag, args.level, args.component, args.grep, args.since)
    result["crashes"] = crashes(args.diag)

    if args.json:
        result["findings"] = result["findings"][: args.top]
        print(json.dumps(result, indent=2))
        return 0

    if result["crashes"]:
        print(f"\n{'!' * 72}\n  {len(result['crashes'])} CRASH LOG(S) — read these before anything else\n{'!' * 72}")
        for c in result["crashes"]:
            print(f"\n  {c['file']}")
            print(f"    signal {c['signal']}  |  {c['version']}  |  thread: {c['crashing_thread']}")
            for fr in c["top_frames"]:
                print(f"      {fr}")

    rows = result["findings"][: args.top]
    if not rows:
        print(f"\nNo messages at level >= {args.level.upper()} matched.")
        print(f"Scanned {result['lines_scanned']:,} lines.")
        return 0

    print(f"\nTop {len(rows)} message patterns at level >= {args.level.upper()}")
    print(f"(scanned {result['lines_scanned']:,} lines, "
          f"{result['lines_unparsed']:,} unparsed continuation lines)\n")
    for i, r in enumerate(rows, 1):
        print(f"{i:3}. [{r['level']:5}] {r['component']}  x{r['count']:,}")
        print(f"     {r['first']}  ->  {r['last']}")
        print(f"     {r['sample']}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
