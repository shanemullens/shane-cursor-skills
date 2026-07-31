#!/usr/bin/env python3
"""Discover Splunk diags under a directory and identify each one.

Finds extracted diag folders and diag tarballs, extracts archives when asked,
and reports hostname, version, OS, roles, and log time window for each.

Usage:
    python3 diag_inventory.py --root . [--extract] [--json]
"""
import argparse
import configparser
import io
import json
import os
import re
import sys
import tarfile
from datetime import datetime

WORKDIR = ".diag-work"
DIAG_MARKERS = ["log/splunkd.log", "etc/splunk.version", "systeminfo.txt", "manifest.csv"]


def is_diag_dir(path):
    """A directory is a diag if it carries at least two of the marker files."""
    hits = sum(1 for m in DIAG_MARKERS if os.path.exists(os.path.join(path, m)))
    return hits >= 2


def find_diags(root, extract=False):
    """Walk root looking for diag directories and diag tarballs."""
    found, archives = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        # don't descend into an identified diag or into our own workdir
        if os.path.basename(dirpath) == WORKDIR:
            dirnames[:] = []
            continue
        if is_diag_dir(dirpath):
            found.append(os.path.abspath(dirpath))
            dirnames[:] = []
            continue
        for fn in filenames:
            if fn.endswith((".tar.gz", ".tgz")) and ("diag" in fn.lower() or "splunk" in fn.lower()):
                archives.append(os.path.abspath(os.path.join(dirpath, fn)))

    for arc in archives:
        dest = os.path.join(root, WORKDIR, os.path.basename(arc).split(".tar")[0])
        if os.path.isdir(dest):
            inner = _descend_to_diag(dest)
            if inner:
                found.append(inner)
            continue
        if not extract:
            found.append({"archive": arc, "extracted": False})
            continue
        os.makedirs(dest, exist_ok=True)
        try:
            with tarfile.open(arc, "r:gz") as tf:
                _safe_extract(tf, dest)
        except Exception as e:  # noqa: BLE001
            found.append({"archive": arc, "error": str(e)})
            continue
        inner = _descend_to_diag(dest)
        if inner:
            found.append(inner)
    return found


def _safe_extract(tf, dest):
    """Extract while refusing paths that escape the destination directory."""
    dest_abs = os.path.abspath(dest)
    for member in tf.getmembers():
        target = os.path.abspath(os.path.join(dest, member.name))
        if not target.startswith(dest_abs + os.sep) and target != dest_abs:
            raise ValueError(f"unsafe path in archive: {member.name}")
        if member.issym() or member.islnk():
            continue
    tf.extractall(dest)


def _descend_to_diag(path):
    """Tarballs usually contain a single top-level diag-<host> directory."""
    if is_diag_dir(path):
        return os.path.abspath(path)
    try:
        entries = [os.path.join(path, e) for e in os.listdir(path)]
    except OSError:
        return None
    subdirs = [e for e in entries if os.path.isdir(e)]
    if len(subdirs) == 1:
        return _descend_to_diag(subdirs[0])
    for d in subdirs:
        if is_diag_dir(d):
            return os.path.abspath(d)
    return None


def read_version(diag):
    """etc/splunk.version holds VERSION, BUILD, PRODUCT."""
    out = {}
    p = os.path.join(diag, "etc", "splunk.version")
    if not os.path.exists(p):
        return out
    for line in _read_text(p).splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


def read_conf(diag, relpath):
    """Parse a Splunk .conf file. Splunk allows duplicate keys and odd chars,
    so fall back to a tolerant manual parse if configparser chokes."""
    p = os.path.join(diag, relpath)
    if not os.path.exists(p):
        return {}
    text = _read_text(p)
    cp = configparser.RawConfigParser(strict=False, allow_no_value=True)
    cp.optionxform = str
    try:
        cp.read_string(text)
        return {s: dict(cp.items(s)) for s in cp.sections()}
    except Exception:  # noqa: BLE001
        return _manual_conf_parse(text)


def _manual_conf_parse(text):
    out, section = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            out.setdefault(section, {})
        elif "=" in line and section is not None:
            k, v = line.split("=", 1)
            out[section][k.strip()] = v.strip()
    return out


def _read_text(path, limit=None):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(limit) if limit else f.read()
    except OSError:
        return ""


def detect_roles(diag):
    """Infer instance roles from conf presence and settings.

    Roles drive which failure modes are plausible, so it's better to report an
    uncertain role than to guess silently.
    """
    roles = []
    ver = read_version(diag)
    product = ver.get("product", "").lower()

    server = read_conf(diag, "etc/system/local/server.conf")
    clustering = server.get("clustering", {})
    mode = clustering.get("mode", "").lower()
    if mode in ("slave", "peer"):
        roles.append("indexer cluster peer")
    elif mode in ("master", "manager"):
        roles.append("cluster manager")
    elif mode == "searchhead":
        roles.append("cluster search head")

    shc = server.get("shclustering", {})
    if shc and shc.get("disabled", "0") not in ("1", "true"):
        roles.append("SHC member")

    if product == "splunkforwarder" or "splunkforwarder" in _read_text(
        os.path.join(diag, "systeminfo.txt"), 4000
    ):
        roles.append("universal forwarder")

    inputs = read_conf(diag, "etc/system/local/inputs.conf")
    outputs = read_conf(diag, "etc/system/local/outputs.conf")
    web = read_conf(diag, "etc/system/local/web.conf")

    if any(k.startswith("splunktcp") for k in inputs):
        roles.append("indexer (receiving)")
    if any(k.startswith("tcpout") for k in outputs):
        roles.append("forwarding")
    if web.get("settings", {}).get("startwebserver", "1") not in ("0", "false"):
        if "universal forwarder" not in roles:
            roles.append("search head / UI")

    if _glob_exists(diag, "etc/system/local/serverclass.conf") or _glob_exists(
        diag, "etc/apps/*/local/serverclass.conf"
    ):
        roles.append("deployment server")
    if _glob_exists(diag, "etc/licenses/enterprise/*"):
        roles.append("license manager (local licenses present)")
    if os.path.isdir(os.path.join(diag, "kvstore")):
        roles.append("kvstore present")

    return sorted(set(roles)) or ["undetermined"]


def _glob_exists(diag, pattern):
    import glob

    return bool(glob.glob(os.path.join(diag, pattern)))


SPLUNKD_TS = re.compile(r"^(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})")


def log_window(diag):
    """First and last timestamp in splunkd.log — the real bound on the analysis."""
    p = os.path.join(diag, "log", "splunkd.log")
    if not os.path.exists(p):
        return {}
    first = last = None
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = SPLUNKD_TS.match(line)
                if m:
                    first = m.group(1)
                    break
        size = os.path.getsize(p)
        with open(p, "rb") as f:
            f.seek(max(0, size - 65536))
            tail = f.read().decode("utf-8", errors="replace")
        for line in reversed(tail.splitlines()):
            m = SPLUNKD_TS.match(line)
            if m:
                last = m.group(1)
                break
    except OSError:
        return {}
    return {"first": first, "last": last, "size_mb": round(os.path.getsize(p) / 1048576, 1)}


def hostname_of(diag):
    server = read_conf(diag, "etc/system/local/server.conf")
    name = server.get("general", {}).get("serverName")
    if name:
        return name
    base = os.path.basename(diag)
    m = re.match(r"diag-(.+?)-\d{4}-\d{2}-\d{2}", base)
    return m.group(1) if m else base


def os_info(diag):
    text = _read_text(os.path.join(diag, "systeminfo.txt"), 200000)
    for line in text.splitlines():
        if line.startswith("Linux ") or line.startswith("Darwin ") or "GNU/Linux" in line:
            return line.strip()[:160]
    m = re.search(r'PRETTY_NAME="([^"]+)"', text)
    return m.group(1) if m else "unknown"


def describe(diag):
    ver = read_version(diag)
    return {
        "path": diag,
        "hostname": hostname_of(diag),
        "version": ver.get("version", "unknown"),
        "build": ver.get("build", "unknown"),
        "product": ver.get("product", "unknown"),
        "os": os_info(diag),
        "roles": detect_roles(diag),
        "log_window": log_window(diag),
        "has_crash_logs": bool(_glob_exists(diag, "log/crash-*.log")),
        "size_mb": round(dir_size(diag) / 1048576, 1),
    }


def dir_size(path):
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for fn in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, fn))
            except OSError:
                pass
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", help="directory to search (default: cwd)")
    ap.add_argument("--extract", action="store_true", help="extract tarballs into .diag-work/")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    raw = find_diags(args.root, extract=args.extract)
    diags, problems = [], []
    for item in raw:
        if isinstance(item, dict):
            problems.append(item)
        else:
            diags.append(describe(item))

    if args.json:
        print(json.dumps({"diags": diags, "unextracted": problems}, indent=2))
        return

    if not diags and not problems:
        print(f"No Splunk diags found under {os.path.abspath(args.root)}")
        print("Looked for directories containing log/splunkd.log + etc/splunk.version,")
        print("and *.tar.gz archives with 'diag' or 'splunk' in the name.")
        return

    for d in diags:
        w = d["log_window"]
        print(f"\n{'=' * 72}")
        print(f"  {d['hostname']}   {d['product']} {d['version']} (build {d['build']})")
        print(f"{'=' * 72}")
        print(f"  path      : {d['path']}")
        print(f"  os        : {d['os']}")
        print(f"  roles     : {', '.join(d['roles'])}")
        if w:
            print(f"  log window: {w.get('first')} -> {w.get('last')}  "
                  f"(splunkd.log {w.get('size_mb')} MB)")
        else:
            print("  log window: splunkd.log not found")
        print(f"  diag size : {d['size_mb']} MB")
        if d["has_crash_logs"]:
            print("  ** crash logs present — read these first (log/crash-*.log)")

    for p in problems:
        if "error" in p:
            print(f"\n  ! failed to extract {p['archive']}: {p['error']}")
        else:
            print(f"\n  ! archive not extracted: {p['archive']}  (re-run with --extract)")


if __name__ == "__main__":
    sys.exit(main())
