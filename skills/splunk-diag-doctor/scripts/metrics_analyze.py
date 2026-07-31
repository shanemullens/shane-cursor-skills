#!/usr/bin/env python3
"""Summarize metrics.log — queue blocking, throughput, tcpout, pipeline cost.

Splunk fails backwards: the queue that reports itself blocked is downstream of
nothing and upstream of everything, so the *last* queue in the chain to block is
usually nearest the real problem. This reports blocking per queue with onset
times so that ordering is visible.

Pipeline chain (data flows down):
    parsingQueue -> aggQueue -> typingQueue -> indexQueue -> [disk]
    tcpout queues sit at the end on forwarders.

Usage:
    python3 metrics_analyze.py --diag <path> [--json]
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict

TS = re.compile(r"^(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})")
KV = re.compile(r"(\w+)=((?:\"[^\"]*\")|(?:[^,\s]+))")

# Canonical downstream order. Anything not listed sorts last.
QUEUE_ORDER = ["parsingqueue", "aggqueue", "typingqueue", "indexqueue", "tcpout"]


def parse_kv(line):
    d = {}
    for k, v in KV.findall(line):
        d[k] = v.strip('"')
    return d


def metrics_files(diag):
    base = os.path.join(diag, "log", "metrics.log")
    rotated = sorted(
        glob.glob(base + ".*"),
        key=lambda p: int(re.sub(r"\D", "", os.path.basename(p)) or 0),
        reverse=True,
    )
    return [p for p in rotated + [base] if os.path.exists(p)]


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def analyze(diag):
    queues = defaultdict(lambda: {
        "samples": 0, "blocked": 0, "max_fill_pct": 0.0, "fill_sum": 0.0,
        "first_blocked": None, "last_blocked": None, "max_size_kb": None,
    })
    pipeline = defaultdict(lambda: {"cpu_seconds": 0.0, "executes": 0})
    tcpout = defaultdict(lambda: {"samples": 0, "kbps_sum": 0.0, "max_kbps": 0.0})
    thruput = {"samples": 0, "kbps_sum": 0.0, "max_kbps": 0.0, "eps_sum": 0.0}
    by_index = defaultdict(float)
    by_sourcetype = defaultdict(float)
    window = {"first": None, "last": None}

    for path in metrics_files(diag):
        try:
            fh = open(path, "r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if "group=" not in line:
                    continue
                mts = TS.match(line)
                ts = mts.group(1) if mts else None
                if ts:
                    if window["first"] is None:
                        window["first"] = ts
                    window["last"] = ts
                d = parse_kv(line)
                group = d.get("group")

                if group == "queue":
                    name = (d.get("name") or "unknown").lower()
                    q = queues[name]
                    q["samples"] += 1
                    maxkb = num(d.get("max_size_kb"))
                    curkb = num(d.get("current_size_kb"))
                    if maxkb > 0:
                        fill = 100.0 * curkb / maxkb
                        q["fill_sum"] += fill
                        q["max_fill_pct"] = max(q["max_fill_pct"], fill)
                        q["max_size_kb"] = maxkb
                    if d.get("blocked", "false").lower() == "true":
                        q["blocked"] += 1
                        if q["first_blocked"] is None:
                            q["first_blocked"] = ts
                        q["last_blocked"] = ts

                elif group == "pipeline":
                    key = f"{d.get('name', '?')}/{d.get('processor', '?')}"
                    pipeline[key]["cpu_seconds"] += num(d.get("cpu_seconds"))
                    pipeline[key]["executes"] += int(num(d.get("executes")))

                elif group == "tcpout_connections":
                    name = d.get("name", "unknown")
                    kbps = num(d.get("_tcp_KBps"))
                    t = tcpout[name]
                    t["samples"] += 1
                    t["kbps_sum"] += kbps
                    t["max_kbps"] = max(t["max_kbps"], kbps)

                elif group == "thruput" and d.get("name") == "index_thruput":
                    kbps = num(d.get("instantaneous_kbps"))
                    thruput["samples"] += 1
                    thruput["kbps_sum"] += kbps
                    thruput["max_kbps"] = max(thruput["max_kbps"], kbps)
                    thruput["eps_sum"] += num(d.get("instantaneous_eps"))

                elif group == "per_index_thruput":
                    by_index[d.get("series", "?")] += num(d.get("kb"))

                elif group == "per_sourcetype_thruput":
                    by_sourcetype[d.get("series", "?")] += num(d.get("kb"))

    for q in queues.values():
        q["avg_fill_pct"] = round(q["fill_sum"] / q["samples"], 1) if q["samples"] else 0.0
        q["max_fill_pct"] = round(q["max_fill_pct"], 1)
        q.pop("fill_sum")

    def qsort(item):
        name = item[0]
        for i, prefix in enumerate(QUEUE_ORDER):
            if name.startswith(prefix):
                return (i, name)
        return (len(QUEUE_ORDER), name)

    return {
        "window": window,
        "queues": dict(sorted(queues.items(), key=qsort)),
        "pipeline_top": sorted(
            ({"stage": k, **v} for k, v in pipeline.items()),
            key=lambda r: -r["cpu_seconds"],
        )[:15],
        "tcpout": {
            k: {"samples": v["samples"],
                "avg_kbps": round(v["kbps_sum"] / v["samples"], 1) if v["samples"] else 0.0,
                "max_kbps": round(v["max_kbps"], 1)}
            for k, v in sorted(tcpout.items(), key=lambda kv: -kv[1]["kbps_sum"])[:15]
        },
        "index_thruput": {
            "samples": thruput["samples"],
            "avg_kbps": round(thruput["kbps_sum"] / thruput["samples"], 1) if thruput["samples"] else 0.0,
            "max_kbps": round(thruput["max_kbps"], 1),
            "avg_eps": round(thruput["eps_sum"] / thruput["samples"], 1) if thruput["samples"] else 0.0,
        },
        "top_indexes_mb": {k: round(v / 1024, 1)
                           for k, v in sorted(by_index.items(), key=lambda kv: -kv[1])[:10]},
        "top_sourcetypes_mb": {k: round(v / 1024, 1)
                               for k, v in sorted(by_sourcetype.items(), key=lambda kv: -kv[1])[:10]},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diag", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(args.diag):
        print(f"Not a directory: {args.diag}", file=sys.stderr)
        return 1
    if not metrics_files(args.diag):
        print("No metrics.log in this diag. Queue and throughput analysis is unavailable —")
        print("say so in the report rather than inferring indexing health from splunkd.log alone.")
        return 0

    r = analyze(args.diag)
    if args.json:
        print(json.dumps(r, indent=2))
        return 0

    w = r["window"]
    print(f"\nmetrics.log window: {w['first']} -> {w['last']}")
    print("(metrics.log rotates aggressively; a short window here bounds every conclusion below)\n")

    print("QUEUES  (listed downstream-last; the last one to block is nearest the cause)")
    print(f"  {'queue':28} {'samples':>8} {'blocked':>8} {'avg%':>6} {'max%':>6}  first blocked")
    for name, q in r["queues"].items():
        flag = "  <<<" if q["blocked"] else ""
        print(f"  {name:28} {q['samples']:>8,} {q['blocked']:>8,} "
              f"{q['avg_fill_pct']:>6} {q['max_fill_pct']:>6}  "
              f"{q['first_blocked'] or '-'}{flag}")

    t = r["index_thruput"]
    if t["samples"]:
        print(f"\nINDEX THRUPUT: avg {t['avg_kbps']} KB/s, peak {t['max_kbps']} KB/s, "
              f"avg {t['avg_eps']} events/s")

    if r["tcpout"]:
        print("\nTCPOUT DESTINATIONS")
        for name, v in r["tcpout"].items():
            print(f"  {name:44} avg {v['avg_kbps']:>8} KB/s  peak {v['max_kbps']:>8} KB/s")

    if r["pipeline_top"]:
        print("\nPIPELINE CPU (top consumers — a regex or parsing hotspot shows up here)")
        for p in r["pipeline_top"][:10]:
            print(f"  {p['stage']:40} {p['cpu_seconds']:>10.1f} cpu-s  "
                  f"{p['executes']:>12,} executes")

    if r["top_sourcetypes_mb"]:
        print("\nTOP SOURCETYPES BY VOLUME (MB in window)")
        for k, v in r["top_sourcetypes_mb"].items():
            print(f"  {k:44} {v:>10,.1f} MB")

    if r["top_indexes_mb"]:
        print("\nTOP INDEXES BY VOLUME (MB in window)")
        for k, v in r["top_indexes_mb"].items():
            print(f"  {k:44} {v:>10,.1f} MB")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
