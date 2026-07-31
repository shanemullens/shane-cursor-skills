# Splunk Diag Analysis — idx01.corp.local (indexer cluster peer, 9.4.1)

**Diag captured:** 2026-07-30  **Log window:** 07-29-2026 10:00 → 15:57  **Analyzed:** 2026-07-31

> Example output produced by running the skill against a synthetic diag. Included to show
> the expected shape of a report, not as guidance for any real deployment.

## Verdict

The index volume `/opt/splunk/var` reached 96% capacity, and at 13:00 on 07-29 index writes
began failing with "No space left on device". This blocked `indexqueue` and cascaded
backpressure through every upstream queue within the same sample interval. High confidence.
The immediate action is reclaiming space on `/opt/splunk/var`; the crash at 13:22 is a
consequence of this condition, not an independent fault.

## Root cause

Disk exhaustion on the index volume. The causal chain is visible end to end in the data:

1. `/opt/splunk/var` at 96% used, 90 GB free of 2.0 TB.
2. From 13:00:11, `IndexProcessor` reports write failures against `defaultdb` (60 occurrences
   through the end of the log window).
3. `indexqueue` blocks from the same minute — 180 of 360 samples blocked, peaking at 100% fill.
4. `typingqueue`, `aggqueue`, and `parsingqueue` block from the same timestamp, which is the
   expected upstream cascade rather than four independent faults.
5. `splunkd` crashes at 13:22 with SIGSEGV in the `indexerPipe` thread — 22 minutes into the
   sustained write-failure condition.

The onset timing is what settles this. Every queue blocked at 13:00:11, and the disk condition
predates it. Nothing upstream started earlier.

**Live alternative:** the crash could be an independent defect that happens to fall inside the
window. Discriminating test — if indexing recovers cleanly once space is reclaimed and no further
crash occurs, the crash was consequential. If `indexerPipe` crashes again on a healthy volume,
escalate the stack against the build separately.

## Evidence

| # | Finding | Severity | Source |
|---|---|---|---|
| 1 | `/opt/splunk/var` at 96% used (90 GB free of 2.0 TB) | Critical | `systeminfo.txt` (df) |
| 2 | `Cannot write to index=main ... No space left on device` ×60, 13:00:11 → 15:57:11 | Critical | `log/splunkd.log` |
| 3 | `indexqueue` blocked 180/360 samples, max fill 100%, first block 13:00:11 | Critical | `log/metrics.log` |
| 4 | Upstream queues blocked from the same timestamp | High | `log/metrics.log` |
| 5 | SIGSEGV in `indexerPipe`, 9.4.1 build e3bdab203ac8, 13:22:01 | High | `log/crash-2026-07-29-13-22-01.log` |
| 6 | `ulimit nofile` = 1024 | Critical | `systeminfo.txt` |
| 7 | Transparent huge pages `enabled` and `defrag` both `always` | High | `systeminfo.txt` |
| 8 | `server.conf [kvstore] storageEngine = mmapv1` | Critical | `etc/system/local/server.conf` |
| 9 | Root filesystem `/` at 94% used | High | `systeminfo.txt` (df) |

## Remediation

### Immediate

Reclaim space on `/opt/splunk/var`. Confirm what is consuming it before deleting anything —
`introspection/disk_objects.log` attributes usage per index, and it is worth knowing whether this
is Splunk data or something else sharing the mount.

Then set retention deliberately rather than relying on disk exhaustion as the policy:

```ini
# $SPLUNK_HOME/etc/system/local/indexes.conf  — restart required
[main]
maxTotalDataSizeMB = 1500000
frozenTimePeriodInSecs = 7776000
```

Verify with `splunk btool indexes list main --debug` and confirm `indexqueue` blocking stops in
`index=_internal source=*metrics.log group=queue`.

### Short term

Raise `nofile` to at least 64000 (finding 6). At 1024 this instance is far below the documented
minimum and will drop forwarder connections under load independently of the disk problem.

```ini
# /etc/systemd/system/Splunkd.service.d/override.conf
[Service]
LimitNOFILE=64000
LimitNPROC=16000
```
`systemctl daemon-reload && systemctl restart Splunkd`, then confirm against the running process
with `cat /proc/$(pgrep -f splunkd | head -1)/limits` — the `/proc` view is the only one that
proves the limit actually applied.

Disable transparent huge pages (finding 7) and make it persist across reboot.

### Preventive

- Migrate KVStore off mmapv1 (finding 8) before the next upgrade — it will fail at the KVStore
  migration step otherwise. This is unrelated to the current incident but is a scheduled outage
  waiting to happen.
- Address `/` at 94% (finding 9) on the same maintenance window.
- Add monitoring on index volume free space with a threshold well above `minFreeSpace` (5000 MB),
  so the alert fires with time to act rather than at the moment indexing halts.

## Secondary findings

Real but not causal here:

- `inputs.conf [WinEventLog://Security] checkpointInterval = 30` — will replay events on any
  ungraceful restart. Given this instance crashed on 07-29, duplicate Windows security events
  around 13:22 are likely. Removing the setting restores per-event checkpointing.
- `limits.conf [thruput] maxKBps = 256` in `myapp` caps forwarding to 256 KB/s.
- `props.conf [bigsourcetype] SHOULD_LINEMERGE = true` — this is the top sourcetype by volume
  (1.76 GB in the window) and `merging/aggregator` dominates pipeline CPU at 4447 cpu-seconds
  against 564 for parsing. Defining `LINE_BREAKER` and disabling line merging is the largest
  available indexing performance win on this host.
- `max_searches_per_cpu` is set in both `system/local` and `myapp/local` with different values
  (2 and 4). Resolve with `splunk btool limits list search --debug`.
- `pass4SymmKey` appears unencrypted in `etc/system/local/server.conf`. Treat this diag as
  containing credential material.

## Not determinable from this diag

- Whether the disk filled gradually or suddenly — the log window starts at 10:00 on 07-29 and the
  volume was already near capacity. A longer window or historical `disk_objects.log` would show
  the growth curve and distinguish organic growth from a runaway source.
- Whether other cluster peers are affected. This is a single peer diag; the cluster manager's view
  and at least one sibling peer would establish whether this is isolated or a shared storage issue.
- Whether the SIGSEGV is a known defect for build `e3bdab203ac8`. That requires a support lookup
  against the build.
