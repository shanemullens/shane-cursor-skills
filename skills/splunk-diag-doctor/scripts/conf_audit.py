#!/usr/bin/env python3
"""Audit the conf layer in a diag for known-bad patterns and precedence conflicts.

This is deliberately rule-driven rather than clever: the RULES table below is the
whole knowledge base and is meant to be extended as you meet new failure modes.
Each rule states what it checks, why it matters, and what to do — so the output
can be pasted almost directly into a remediation section.

Precedence note: this does NOT reimplement btool. It reports *where* a setting is
defined and flags when the same stanza+key is set in multiple app-local files,
which is the situation where operators reliably guess wrong about which wins.

Usage:
    python3 conf_audit.py --diag <path> [--conf outputs.conf] [--json]
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict

SECRET_KEYS = re.compile(
    r"(pass4symmkey|sslpassword|password|bindDNpassword|secret|token|apikey|api_key)",
    re.I)
ENCRYPTED = re.compile(r"^\$[1-9]\$")


def parse_conf(path):
    """Tolerant Splunk conf parser. Returns {stanza: {key: value}}."""
    out, section = {}, "default"
    out[section] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return {}
    buf = ""
    for raw in lines:
        line = raw.rstrip()
        if line.endswith("\\"):           # conf files allow line continuation
            buf += line[:-1]
            continue
        line = (buf + line).strip()
        buf = ""
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            out.setdefault(section, {})
        elif "=" in line:
            k, v = line.split("=", 1)
            out.setdefault(section, {})[k.strip()] = v.strip()
    return {k: v for k, v in out.items() if v or k != "default"}


def collect(diag):
    """Gather every conf file with its scope. Later scopes win in Splunk's
    precedence for most contexts, but app ordering is alphabetical and messy —
    hence the conflict reporting rather than a verdict."""
    layers = [
        ("system/default", "etc/system/default/*.conf"),
        ("app/default", "etc/apps/*/default/*.conf"),
        ("app/local", "etc/apps/*/local/*.conf"),
        ("user", "etc/users/*/*/local/*.conf"),
        ("system/local", "etc/system/local/*.conf"),
    ]
    store = defaultdict(list)   # conf_name -> [(scope, relpath, parsed)]
    for scope, pattern in layers:
        for path in sorted(glob.glob(os.path.join(diag, pattern))):
            name = os.path.basename(path)
            rel = os.path.relpath(path, diag)
            store[name].append((scope, rel, parse_conf(path)))
    return store


def gt(val, threshold):
    try:
        return float(val) > threshold
    except (TypeError, ValueError):
        return False


def lt(val, threshold):
    try:
        return float(val) < threshold
    except (TypeError, ValueError):
        return False


# (conf, stanza_regex, key, predicate, severity, message)
# predicate receives the value string; None means "flag whenever key is present".
RULES = [
    ("limits.conf", r"^thruput$", "maxKBps",
     lambda v: v not in ("0",) and lt(v, 1024), "High",
     "Forwarder throughput is throttled. Default on a universal forwarder is 256 KB/s, "
     "which silently caps ingestion and looks exactly like a network or indexer problem. "
     "Set maxKBps = 0 for unlimited on hosts where the UF is expected to move real volume."),

    ("outputs.conf", r"^tcpout", "useACK",
     lambda v: v.lower() in ("true", "1"), "Medium",
     "Indexer acknowledgement is on. It protects against data loss but roughly triples "
     "memory per output queue and will block the pipeline when indexers are slow. If "
     "queues are blocking, this amplifies the symptom — confirm it is a deliberate choice."),

    ("outputs.conf", r"^tcpout", "autoLBFrequency",
     lambda v: gt(v, 120), "Medium",
     "autoLBFrequency is high, so a forwarder stays pinned to one indexer for a long "
     "time. This produces uneven indexer load and skewed search performance."),

    ("inputs.conf", r"^WinEventLog", "checkpointInterval",
     lambda v: gt(v, 0), "High",
     "checkpointInterval on a WinEventLog input delays checkpoint writes, so any "
     "ungraceful restart replays events already indexed. This is the usual root cause "
     "of duplicate Windows security events on domain controllers. Remove the setting "
     "(default 0 = checkpoint every event) unless there is a measured I/O reason."),

    ("indexes.conf", r".*", "maxTotalDataSizeMB",
     lambda v: gt(v, 4000000), "Medium",
     "maxTotalDataSizeMB is very large. Retention will be governed by disk exhaustion "
     "rather than policy, and the first symptom is indexing halting on minFreeSpace."),

    ("server.conf", r"^queue", "maxSize",
     None, "Info",
     "A queue size override is present. Enlarging queues hides backpressure rather than "
     "fixing it — confirm the downstream cause was addressed."),

    ("server.conf", r"^kvstore$", "storageEngine",
     lambda v: v.lower() == "mmapv1", "Critical",
     "KVStore is on the mmapv1 storage engine, which is removed in modern Splunk. "
     "Upgrades will fail at the KVStore migration step until this is migrated to "
     "wiredTiger."),

    ("limits.conf", r"^search$", "max_searches_per_cpu",
     lambda v: gt(v, 1), "Medium",
     "max_searches_per_cpu is raised above default. This inflates search concurrency "
     "beyond what the hardware supports and typically converts skipped searches into "
     "system-wide slowness."),

    ("limits.conf", r"^scheduler$", "max_searches_perc",
     lambda v: gt(v, 75), "Medium",
     "Scheduler is allowed a large share of total search capacity, starving ad-hoc "
     "searches. Users experience this as the UI being unusable while everything looks "
     "healthy server-side."),

    ("deploymentclient.conf", r"^deployment-client$", "phoneHomeIntervalInSecs",
     lambda v: lt(v, 60), "Medium",
     "Clients phone home very frequently. On a deployment server with many clients this "
     "saturates the DS and causes reload storms."),

    ("props.conf", r".*", "SHOULD_LINEMERGE",
     lambda v: v.lower() in ("true", "1"), "Medium",
     "SHOULD_LINEMERGE is enabled for this sourcetype. Line merging is the single most "
     "expensive parsing operation in Splunk. If this sourcetype is high volume, defining "
     "LINE_BREAKER and setting SHOULD_LINEMERGE = false is usually the largest available "
     "indexing performance win."),

    ("props.conf", r".*", "DATETIME_CONFIG",
     lambda v: "NONE" in v.upper(), "Medium",
     "Timestamp extraction is disabled for this sourcetype, so events take index time as "
     "their timestamp. If users report events at the wrong time, start here."),

    ("props.conf", r".*", "MAX_DAYS_AGO",
     lambda v: gt(v, 2000), "Low",
     "MAX_DAYS_AGO is set very high, which lets misparsed timestamps land far in the past "
     "and create buckets that distort retention."),

    ("web.conf", r"^settings$", "enableSplunkWebSSL",
     lambda v: v.lower() in ("false", "0"), "Medium",
     "Splunk Web is serving over plain HTTP. Credentials cross the network in the clear."),
]


def audit(diag, only_conf=None):
    store = collect(diag)
    findings, secrets = [], []
    key_locations = defaultdict(list)   # (conf, stanza, key) -> [scope:file]

    for conf_name, entries in store.items():
        if only_conf and conf_name != only_conf:
            continue
        for scope, rel, parsed in entries:
            for stanza, kvs in parsed.items():
                for key, value in kvs.items():
                    if scope in ("app/local", "system/local", "user"):
                        key_locations[(conf_name, stanza, key)].append(f"{scope}:{rel}")
                    if SECRET_KEYS.search(key) and value and not ENCRYPTED.match(value):
                        secrets.append({"file": rel, "stanza": stanza, "key": key,
                                        "note": "value appears unencrypted — not shown"})
                    for r_conf, r_stanza, r_key, pred, sev, msg in RULES:
                        if conf_name != r_conf or key != r_key:
                            continue
                        if not re.match(r_stanza, stanza):
                            continue
                        if pred is not None and not pred(value):
                            continue
                        findings.append({
                            "severity": sev, "conf": conf_name, "stanza": stanza,
                            "key": key, "value": value, "scope": scope,
                            "source": rel, "message": msg,
                        })

    conflicts = [
        {"conf": k[0], "stanza": k[1], "key": k[2], "defined_in": v}
        for k, v in key_locations.items() if len(set(v)) > 1
    ]
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}
    findings.sort(key=lambda f: order.get(f["severity"], 9))
    return {"findings": findings, "conflicts": conflicts,
            "unencrypted_secrets": secrets,
            "conf_files_scanned": sum(len(v) for v in store.values())}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diag", required=True)
    ap.add_argument("--conf", help="restrict to a single conf file, e.g. outputs.conf")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(args.diag):
        print(f"Not a directory: {args.diag}", file=sys.stderr)
        return 1

    r = audit(args.diag, args.conf)
    if args.json:
        print(json.dumps(r, indent=2))
        return 0

    print(f"\nScanned {r['conf_files_scanned']} conf files.\n")

    if r["findings"]:
        print(f"RULE HITS ({len(r['findings'])})\n")
        for f in r["findings"]:
            print(f"[{f['severity']:8}] {f['conf']} [{f['stanza']}] {f['key']} = {f['value']}")
            print(f"           source: {f['source']}")
            print(f"           {f['message']}")
            print()
    else:
        print("No rule hits. Note this is a finite rule set — absence of hits is not a "
              "clean bill of health for the conf layer.\n")

    if r["conflicts"]:
        print(f"PRECEDENCE CONFLICTS ({len(r['conflicts'])}) — same key set in multiple "
              f"local scopes\n")
        for c in r["conflicts"][:25]:
            print(f"  {c['conf']} [{c['stanza']}] {c['key']}")
            for loc in sorted(set(c["defined_in"])):
                print(f"      {loc}")
            print()

    if r["unencrypted_secrets"]:
        print(f"POSSIBLE PLAINTEXT SECRETS ({len(r['unencrypted_secrets'])}) — values "
              f"withheld deliberately\n")
        for s in r["unencrypted_secrets"][:25]:
            print(f"  {s['file']}  [{s['stanza']}]  {s['key']}")
        print("\n  Do not copy these values anywhere. Flag to the customer that the diag "
              "contains credential material and should be handled accordingly.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
