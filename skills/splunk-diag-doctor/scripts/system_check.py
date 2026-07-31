#!/usr/bin/env python3
"""OS-level checks against systeminfo.txt.

Ulimits and transparent huge pages account for a large share of "Splunk is
inexplicably slow / dropping connections / crashing under load" cases, and both
are invisible from inside Splunk itself. Run this even when the reported symptom
sounds purely application-level.

systeminfo.txt formatting varies across Splunk versions and platforms, so every
check reports "not found" rather than guessing when it cannot locate a value.

Usage:
    python3 system_check.py --diag <path> [--json]
"""
import argparse
import json
import os
import re
import sys

# Splunk's documented minimums for Linux. See docs: "Configure ulimits for Splunk Enterprise".
ULIMIT_RULES = {
    "open files": (64000, "nofile", "Too few file descriptors causes dropped forwarder "
                                    "connections, failed bucket opens, and search failures "
                                    "under concurrency."),
    "max user processes": (16000, "nproc", "Splunk forks a process per search; hitting nproc "
                                           "produces search failures that look like resource "
                                           "exhaustion with no clear error."),
    "data seg size": (1073741824, "data", "A capped data segment starves large searches and "
                                          "index-time operations."),
    "file size": (-1, "fsize", "A file size cap truncates journal and tsidx writes, which "
                               "corrupts buckets."),
}


def read_systeminfo(diag):
    for candidate in ("systeminfo.txt", os.path.join("systeminfo", "systeminfo.txt")):
        p = os.path.join(diag, candidate)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    return f.read()
            except OSError:
                return ""
    return ""


def finding(severity, title, observed, recommended, why, source="systeminfo.txt"):
    return {"severity": severity, "title": title, "observed": observed,
            "recommended": recommended, "why": why, "source": source}


def check_ulimits(text):
    out = []
    for label, (minimum, flag, why) in ULIMIT_RULES.items():
        # Anchor to line start so "file size" doesn't match "core file size".
        m = re.search(rf"^\s*{re.escape(label)}\s*\([^)]*\)\s*(\S+)", text, re.I | re.M)
        if not m:
            out.append(finding("Info", f"ulimit '{label}' not found in systeminfo.txt",
                               "not found", f"{'unlimited' if minimum == -1 else minimum}",
                               "Cannot confirm; check with `ulimit -a` as the splunk user."))
            continue
        raw = m.group(1)
        if raw.lower() == "unlimited":
            continue
        try:
            val = int(raw)
        except ValueError:
            continue
        # 'data seg size' and 'file size' report in KB/blocks respectively.
        if label == "data seg size":
            val *= 1024
        if minimum == -1:
            out.append(finding("High", f"ulimit {flag} is capped, not unlimited",
                               raw, "unlimited", why))
        elif val < minimum:
            sev = "Critical" if val < minimum / 4 else "High"
            out.append(finding(sev, f"ulimit {flag} below Splunk minimum",
                               raw, f">= {minimum}", why))
    return out


def check_thp(text):
    out = []
    found = False
    for line in text.splitlines():
        if "transparent_hugepage" in line and ("enabled" in line or "defrag" in line):
            found = True
            active = re.search(r"\[(\w+)\]", line)
            state = active.group(1) if active else line.split(":")[-1].strip()
            which = "enabled" if "enabled" in line else "defrag"
            if state.lower() != "never":
                out.append(finding(
                    "High", f"Transparent huge pages ({which}) is '{state}', not 'never'",
                    state, "never",
                    "THP causes memory stalls and latency spikes in Splunk's allocation "
                    "patterns. Splunk explicitly requires it disabled; symptoms are erratic "
                    "search latency and high system CPU with no matching workload.",
                    line.strip()[:120]))
    if not found:
        out.append(finding("Info", "Transparent huge pages state not found",
                           "not found", "never",
                           "Verify with: cat /sys/kernel/mm/transparent_hugepage/enabled"))
    return out


DF_LINE = re.compile(
    r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\d+)%\s+(\S+)\s*$", re.M)


def check_disk(text):
    out = []
    seen = False
    for m in DF_LINE.finditer(text):
        fs, size, used, avail, pct, mount = m.groups()
        seen = True
        pct = int(pct)
        if pct >= 95:
            sev = "Critical"
        elif pct >= 85:
            sev = "High"
        elif pct >= 75:
            sev = "Medium"
        else:
            continue
        note = ("Splunk stops indexing when free space on an index volume drops below "
                "minFreeSpace (default 5000 MB). At this utilization that threshold is "
                "close, and hitting it halts ingestion rather than degrading it.")
        out.append(finding(sev, f"Filesystem {mount} at {pct}% used",
                           f"{used} used of {size}, {avail} available", "< 75% used",
                           note, f"df: {fs} -> {mount}"))
    if not seen:
        out.append(finding("Info", "No df output found in systeminfo.txt",
                           "not found", "-", "Check disk utilization directly on the host."))
    return out


def check_memory_cpu(text):
    out = []
    mem = re.search(r"MemTotal:\s+(\d+)\s*kB", text)
    if mem:
        gb = int(mem.group(1)) / 1048576
        if gb < 11.5:
            out.append(finding(
                "High", "System memory below Splunk reference hardware",
                f"{gb:.1f} GB", ">= 12 GB",
                "Splunk's reference server spec is 12 GB RAM. Below this, search "
                "concurrency and KVStore both degrade sharply."))
    swap = re.search(r"SwapTotal:\s+(\d+)\s*kB", text)
    swapfree = re.search(r"SwapFree:\s+(\d+)\s*kB", text)
    if swap and swapfree:
        total, free = int(swap.group(1)), int(swapfree.group(1))
        if total > 0 and (total - free) / total > 0.25:
            out.append(finding(
                "High", "Significant swap in use",
                f"{(total - free) / 1048576:.1f} GB of {total / 1048576:.1f} GB swap used",
                "minimal swap usage",
                "Splunk performance collapses once it swaps. Sustained swap use points at "
                "memory pressure — often too many concurrent searches or an oversized KVStore."))

    cpus = len(re.findall(r"^processor\s*:", text, re.M))
    if not cpus:
        m = re.search(r"CPU\(s\):\s*(\d+)", text)
        cpus = int(m.group(1)) if m else 0
    if cpus and cpus < 12:
        out.append(finding(
            "Medium", "CPU core count below Splunk reference hardware",
            f"{cpus} cores", ">= 12 cores",
            "Reference spec is 12 CPU cores. Fewer cores caps search concurrency "
            "(base_max_searches plus per-core multiplier) and indexing pipeline throughput."))
    return out


def check_misc(text):
    out = []
    m = re.search(r"vm\.max_map_count\s*=\s*(\d+)", text)
    if m and int(m.group(1)) < 262144:
        out.append(finding(
            "Medium", "vm.max_map_count below recommended",
            m.group(1), ">= 262144",
            "Low max_map_count causes bucket mmap failures on indexers with many buckets."))
    m = re.search(r"SELinux status:\s*(\w+)", text)
    if m and m.group(1).lower() == "enabled":
        mode = re.search(r"Current mode:\s*(\w+)", text)
        if mode and mode.group(1).lower() == "enforcing":
            out.append(finding(
                "Medium", "SELinux is enforcing",
                "enforcing", "permissive, or a validated Splunk policy",
                "Enforcing SELinux without a Splunk policy blocks port binding, "
                "helper scripts, and KVStore startup in ways that surface as opaque "
                "permission errors in splunkd.log."))
    return out


SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diag", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    text = read_systeminfo(args.diag)
    if not text:
        print("systeminfo.txt not found or empty in this diag.")
        print("OS-level checks are unavailable — note this explicitly in the report.")
        return 0

    findings = (check_ulimits(text) + check_thp(text) + check_disk(text)
                + check_memory_cpu(text) + check_misc(text))
    findings.sort(key=lambda f: SEV_ORDER.get(f["severity"], 9))

    if args.json:
        print(json.dumps({"findings": findings}, indent=2))
        return 0

    real = [f for f in findings if f["severity"] != "Info"]
    print(f"\nOS-level findings: {len(real)} actionable, "
          f"{len(findings) - len(real)} informational\n")
    for f in findings:
        print(f"[{f['severity']:8}] {f['title']}")
        print(f"           observed: {f['observed']}   recommended: {f['recommended']}")
        print(f"           {f['why']}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
