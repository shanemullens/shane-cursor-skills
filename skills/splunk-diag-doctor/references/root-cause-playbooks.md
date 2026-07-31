# Root cause playbooks

One playbook per recurring failure class. Each gives the evidence to gather, the causes
ranked by how often they turn out to be it, and the test that discriminates between them.

Work the discriminating test rather than accumulating supporting evidence. A busy Splunk
instance contains enough warnings to "confirm" any hypothesis you walk in with.

## Contents

1. [Indexing lag / blocked queues](#1-indexing-lag--blocked-queues)
2. [Indexing stopped entirely](#2-indexing-stopped-entirely)
3. [Skipped scheduled searches](#3-skipped-scheduled-searches)
4. [Search head slow or unresponsive](#4-search-head-slow-or-unresponsive)
5. [KVStore will not start](#5-kvstore-will-not-start)
6. [SSL and certificate failures](#6-ssl-and-certificate-failures)
7. [Indexer cluster unhealthy](#7-indexer-cluster-unhealthy)
8. [Search head cluster instability](#8-search-head-cluster-instability)
9. [Forwarder not sending data](#9-forwarder-not-sending-data)
10. [Duplicate events](#10-duplicate-events)
11. [Missing events or wrong timestamps](#11-missing-events-or-wrong-timestamps)
12. [splunkd crashes](#12-splunkd-crashes)
13. [License violations](#13-license-violations)
14. [Deployment server overload](#14-deployment-server-overload)
15. [Upgrade failures](#15-upgrade-failures)

---

## 1. Indexing lag / blocked queues

**Reported as:** data arriving late, `_indextime` far behind `_time`, dashboards stale.

**Evidence:** `metrics_analyze.py` queue table; `splunkd.log` for `IndexProcessor`,
`TcpOutputProc`; `systeminfo.txt` disk; `introspection/resource_usage.log`.

**The key reasoning move:** queues block backwards. Data flows
`parsing → agg → typing → index → disk`. When `indexqueue` blocks, everything upstream
blocks behind it. So **the furthest-downstream blocked queue points at the cause**, and
every queue upstream of it is a symptom.

| Furthest blocked | What it means | Ranked causes |
|---|---|---|
| `indexqueue` | Splunk can't write to disk fast enough | 1. Slow or saturated storage (check IOPS, `df`, SAN). 2. Too few index pipelines for the volume. 3. Disk near full. |
| `typingqueue` | regex replacement cost | 1. Expensive `SEDCMD` or `transforms` regex. 2. Excessive index-time field extraction. |
| `aggqueue` | line merging cost | 1. `SHOULD_LINEMERGE=true` on a high-volume sourcetype. 2. No `LINE_BREAKER` defined, forcing default merge logic. |
| `parsingqueue` | timestamp/charset cost | 1. Timestamp parsing failures forcing full-event scans. 2. Missing `TIME_FORMAT`/`TIME_PREFIX`. |
| `tcpout_*` (on a forwarder) | downstream won't accept | 1. Indexer blocked (repeat this analysis there). 2. Network. 3. `maxKBps` throttle. 4. `useACK` with slow indexers. |

**Discriminating tests:**
- Cross-check `group=pipeline` cpu_seconds. A single processor dominating confirms a
  parsing cost problem rather than a disk problem.
- If *all* queues blocked simultaneously with no downstream signal, suspect the host:
  CPU saturation, swap, or a stalled `WatchdogThread` in `splunkd.log`.
- On a cluster, check whether peers block together (shared storage or CM) or one alone
  (that host's disk).

**Common wrong conclusion:** enlarging queue sizes in `server.conf`. That buys seconds of
buffering and hides the signal. Only do it as a deliberate burst-absorption measure after
the actual bottleneck is fixed.

---

## 2. Indexing stopped entirely

**Reported as:** no new events at all, often quite abruptly.

**Evidence:** `splunkd.log` for `IndexProcessor` / `DatabaseDirectoryManager`;
`systeminfo.txt` df; `disk_objects.log`; license logs.

**Ranked causes:**
1. **Free space below `minFreeSpace`.** Splunk halts indexing rather than filling the disk.
   Default is 5000 MB. Look for messages about insufficient disk space to continue.
   This is by far the most common cause and `system_check.py` catches it.
2. **License violation lockout** — on older versions, repeated violations restricted search.
   Modern versions warn rather than stop indexing, so verify the version before claiming it.
3. **Maximum bucket or index size reached** with no roll path available.
4. **Permissions** — Splunk running as a user that lost write access to the index path,
   frequently after an upgrade or a `chown` during maintenance.
5. **Cluster peer refusing writes** because it can't reach the manager and has passed its
   restart timeout.

**Discriminating test:** the last `metrics.log` `group=thruput` sample time versus the diag
capture time gives the exact stop moment. Line the `splunkd.log` ERROR sequence up to that
timestamp — the cause is in the 60 seconds before, not after.

---

## 3. Skipped scheduled searches

**Reported as:** alerts not firing, summary indexes with gaps.

**Evidence:** `scheduler.log` grouped by `reason=`; `limits.conf`; CPU count from
`systeminfo.txt`.

The `reason=` string is the finding. Map it:

| Reason contains | Root cause | Fix direction |
|---|---|---|
| maximum number of concurrent running jobs | Total search concurrency ceiling reached | Raise capacity (cores) or reduce scheduled load; retune `base_max_searches` only with care |
| for this historical scheduled search | Per-search concurrency — the previous run hadn't finished | The search is too slow for its schedule; fix the search or lengthen the interval |
| maximum number of concurrent scheduled searches | Scheduler's share of capacity exhausted | `max_searches_perc` in `limits.conf [scheduler]` |
| The search was not run because it was disabled | Someone disabled it | Not a performance issue |
| skipped due to reaching the disk quota | User or role `srchDiskQuota` | `authorize.conf` |

**Reason the concurrency math matters:** total concurrent searches defaults to
`base_max_searches` (6) plus `max_searches_per_cpu` (1) × cores. On a 4-core box that's 10
total, of which the scheduler gets a percentage. Undersized hardware plus an enthusiastic
app install produces skips that look like a Splunk bug and are pure arithmetic.

**Discriminating test:** correlate skip timestamps against `resource_usage.log`. Skips at
low CPU mean a configured limit; skips at pegged CPU mean genuine resource exhaustion, and
raising limits will make it worse.

---

## 4. Search head slow or unresponsive

**Evidence:** `dispatch/` directory count, `resource_usage.log` PerProcess, `splunkd.log`
for `DispatchManager` and `SearchOrchestrator`, KVStore state.

**Ranked causes:**
1. **Dispatch directory bloat** — tens of thousands of artifacts make every directory scan
   expensive. Check the count of subdirectories under `dispatch/`. Above ~10,000 is a
   problem; the cause is usually long `dispatch.ttl` combined with high scheduled volume.
2. **One expensive search** consuming the box — `resource_usage.log` PerProcess names the
   search ID; correlate to `audit.log` or `dispatch/<sid>/info.csv` for the SPL.
3. **KVStore problems** — a struggling KVStore makes the entire UI sluggish because lookups
   and app state live there.
4. **Bundle replication** — large knowledge bundles pushed to many peers repeatedly. Look
   for bundle size warnings in `splunkd.log`.
5. **Memory pressure and swap** — from `system_check.py`.

---

## 5. KVStore will not start

**Evidence:** `mongod.log`, `splunkd.log` for `KVStoreConfigurationProvider` and
`MongodRunner`, `kvstore/` directory, `server.conf [kvstore]`.

**Ranked causes:**
1. **Storage engine migration not done.** `storageEngine = mmapv1` blocks upgrades to
   versions where only wiredTiger is supported. `conf_audit.py` flags this as Critical.
2. **Expired KVStore certificate.** Splunk's internal `server.pem` expires; mongod refuses
   to start with a TLS error. Extremely common on long-lived instances and easy to miss
   because the message is a mongod-level SSL error, not an obvious Splunk one.
3. **Unclean shutdown / lock file** left behind after a crash or a hard power loss.
4. **Port conflict** on 8191.
5. **Insufficient disk** in `var/lib/splunk/kvstore`.
6. **SHC members disagreeing** — replication stalled, one member never reaching primary.

**Discriminating test:** `mongod.log` has the actual reason and it is usually explicit.
Read it before theorizing from `splunkd.log`, which only reports that the child failed.

---

## 6. SSL and certificate failures

**Evidence:** `splunkd.log` for `SSLCommon`, `X509Verify`, `HttpListener`; `server.conf`,
`inputs.conf`, `outputs.conf`, `web.conf` SSL stanzas; `systeminfo.txt` for library paths.

**Ranked causes:**
1. **Expired certificate** — default Splunk certs are valid 3 years and expire quietly.
   Affects internal communication first: forwarder-to-indexer, SHC, KVStore.
2. **Certificate/CA mismatch** after replacing certs on one tier but not another.
3. **Hostname verification** — `sslVerifyServerName = true` with certs whose CN/SAN doesn't
   match the connecting name.
4. **TLS version or cipher mismatch** after hardening, especially where one side is an
   older forwarder.
5. **Wrong OpenSSL library being resolved.** `splunkd` ships its own libcrypto/libssl under
   `$SPLUNK_HOME/lib`. If it binds the system library instead, symptoms are bizarre: FIPS
   errors, unresolved symbols, or startup failure. On Linux this happens when the binary
   has setuid bits or file capabilities set, which trips glibc's secure-execution mode and
   causes `$ORIGIN`/`RPATH` in `LD_LIBRARY_PATH` to be ignored. Check for capabilities on
   `splunkd` and for a `SPLUNK_HOME/lib` entry that is being dropped.

**Discriminating test:** the error text distinguishes these cleanly — expiry says expired,
verification failure names the depth and subject, library resolution fails at load time
before any handshake. Get the exact message rather than working from the category.

---

## 7. Indexer cluster unhealthy

**Evidence:** CM `splunkd.log` for `CMMaster`; peer `splunkd.log` for `CMPeer` and
`CMRepJob`; compare across all peer diags.

**Ranked causes:**
1. **Replication or search factor not met** because a peer is down, or because there aren't
   enough peers for the configured RF/SF. Fixup counts in `CMMaster` messages tell you
   whether the cluster is actively repairing or stuck.
2. **Fixup stuck on specific buckets** — usually one peer with a full or failing disk, or a
   bucket that can't be replicated because no source copy is available.
3. **Peer/manager connectivity** — `pass4SymmKey` mismatch, DNS, firewall on 8089, or clock
   skew large enough to break authentication.
4. **Rolling restart loop** — peers restarting continuously, often triggered by a bundle
   push that fails validation on some peers.
5. **Site/multisite misconfiguration** — `site_replication_factor` unsatisfiable given the
   peers actually present.

**Cross-diag test:** compare `server.conf [clustering]` across every peer diag. Drift in
`pass4SymmKey` (present vs absent), `site`, or `replication_factor` is a frequent and
easily-missed root cause. `conf_audit.py --json` output diffs cleanly for this.

---

## 8. Search head cluster instability

**Evidence:** `splunkd.log` for `SHCMaster`, `SHCRaft`, `SHPMaster`; `consensus/`;
`mongod.log`.

**Ranked causes:**
1. **Captain election churn** — usually network latency between members or clock skew.
   Raft is sensitive to both.
2. **KVStore replication failure** blocking member readiness.
3. **Insufficient members for quorum** — a 3-member cluster with one down is fragile, with
   two down is dead.
4. **Bundle replication failures** between members, often a size or disk problem.
5. **`pass4SymmKey` mismatch** in the `[shclustering]` stanza specifically — distinct from
   the general one, and mixing them up is a classic mistake.

**Time sync note:** check NTP state in `systeminfo.txt` early here. Clock skew produces
symptoms across raft, TLS, and search that look unrelated to each other.

---

## 9. Forwarder not sending data

**Evidence:** forwarder `splunkd.log` for `TcpOutputProc`; `metrics.log`
`group=tcpout_connections` and `group=queue`; `outputs.conf`; `inputs.conf`.

**Ranked causes:**
1. **Indexer side blocked** — the forwarder is fine, the receiver isn't accepting. Analyze
   the indexer diag instead; playbook 1.
2. **Throughput throttle** — `limits.conf [thruput] maxKBps`. The universal forwarder
   default of 256 KB/s is deliberate and frequently forgotten. It looks exactly like a
   network problem: steady, capped, unexplained.
3. **Connectivity** — DNS, firewall, wrong port, TLS mismatch.
4. **Input not actually reading** — file permissions, wrong path, blacklist, or a monitor
   input whose checkpoint says it already read everything.
5. **`useACK` with slow indexers** — the wait for acknowledgement stalls the output queue.
6. **Queue full upstream** on a heavy forwarder doing parsing work.

**Discriminating test:** `group=thruput` on the forwarder tells you whether data is being
*read* at all. Reading but not sending is 1/2/3/5. Not reading is 4.

---

## 10. Duplicate events

**Evidence:** `inputs.conf`, `outputs.conf`, forwarder `splunkd.log`, deployment topology.

**Ranked causes:**
1. **Checkpoint replay.** Any input with a delayed checkpoint replays on ungraceful restart.
   `checkpointInterval` on WinEventLog inputs is the classic case: the interval defers
   checkpoint writes, so a crash re-reads everything since the last one. `conf_audit.py`
   flags it.
2. **Two forwarders monitoring the same path** — often a UF plus a leftover HF, or a shared
   NFS mount monitored from several hosts.
3. **Cloned output groups** in `outputs.conf` sending to two destinations that both index.
4. **File rotation confusing the CRC** — `crcSalt`, `initCrcLength`, or files whose first
   256 bytes are identical (headers) causing re-reads as new files.
5. **Re-indexing after a rebuild** where `fishbucket` was reset.

**Discriminating test:** if duplicates cluster around restart times, it's 1. If they're
continuous, it's 2 or 3. If they appear at log rotation boundaries, it's 4.

---

## 11. Missing events or wrong timestamps

**Evidence:** `splunkd.log` for `DateParserVerbose`, `AggregatorMiningProcessor`,
`LineBreakingProcessor`; `props.conf`.

**Ranked causes:**
1. **Timestamp parsing failure** — events land at index time or at a wildly wrong time.
   `DateParserVerbose` warnings name the source. Fix with explicit `TIME_PREFIX`,
   `TIME_FORMAT`, and `MAX_TIMESTAMP_LOOKAHEAD`.
2. **Events outside `MAX_DAYS_AGO` / `MAX_DAYS_HENCE`** get discarded or clamped, so they
   appear "missing" while indexing reports success.
3. **Line breaking wrong** — multi-line events merged or split, so searches for a field
   miss. Look for `LINE_BREAKER` absent on a sourcetype with `SHOULD_LINEMERGE=true`.
4. **`TRUNCATE`** (default 10000 bytes) silently cutting long events.
5. **Timezone** — no `TZ` in props and the forwarder host in a different zone than assumed.
6. **License violation** on old versions, or an index that rolled/froze data early because
   of `frozenTimePeriodInSecs`.

---

## 12. splunkd crashes

**Evidence:** `crash-*.log` in full; `splunkd.log` for the 5 minutes before each crash;
`systeminfo.txt` memory; `resource_usage.log`.

**Read the crash log first.** It names the signal, the crashing thread, and the top stack
frames, and those three narrow the cause dramatically:

- **Signal 11 (SEGV) in a search thread** — often a specific search or a custom command.
  Correlate the crash time to `audit.log` for what was running.
- **Signal 6 (ABRT)** — assertion failure, frequently a bucket integrity problem.
- **Signal 9 (KILL)** — not a crash. This is the OOM killer. Confirm in the host's syslog
  and treat it as memory exhaustion, not a Splunk defect.
- **Crashing thread `indexerPipe`** — indexing path, look at bucket state and disk.
- **Repeated identical crashes** at a fixed interval suggest a scheduled search trigger.

Always report the exact version and build alongside the stack. A known fixed defect is a
realistic outcome here, and the version is what makes that determinable.

---

## 13. License violations

**Evidence:** `splunkd.log` for `LMTracker`, `LMStackMgr`; `license_usage.log`;
`etc/licenses/`.

**Ranked causes:**
1. Genuine volume growth past the license quota.
2. A new noisy source added — `metrics_analyze.py` top sourcetypes by volume identifies it
   immediately, and this is usually the fastest win in the whole report.
3. Duplicate ingestion inflating counted volume (playbook 10).
4. License manager unreachable, so peers enter a grace period that looks like a violation.
5. Pool misconfiguration where one pool is starved while another has headroom.

Distinguish warnings from violations, and know the version's behavior: modern Splunk does
not block search on Enterprise licenses the way older versions did. Overstating the
consequence here damages credibility with a customer.

---

## 14. Deployment server overload

**Evidence:** `splunkd.log` for `DeployedServerclass`, `DeployedApplication`, `DC:*`
handlers; `serverclass.conf`; `deploymentclient.conf` on clients.

**Ranked causes:**
1. **Too many clients for one DS** with default settings. Past roughly 2,000 clients this
   needs deliberate tuning.
2. **`phoneHomeIntervalInSecs` too low** across many clients, producing constant load.
3. **Large apps being pushed repeatedly** — check app sizes in the deployment-apps path.
4. **Serverclass reload storms** — every reload recalculates the full client-to-app map.
5. **Whitelist/blacklist by wildcard hostname** forcing expensive matching per phone-home.

---

## 15. Upgrade failures

**Evidence:** `splunkd.log` startup sequence, `mongod.log`, `btool.log`,
`etc/splunk.version`, migration logs.

**Ranked causes:**
1. **KVStore migration** — mmapv1 to wiredTiger, or a mongod version step that requires an
   intermediate upgrade. Playbook 5.
2. **Conf incompatibility** — settings removed or renamed in the new version. `btool.log`
   reports these at startup and is frequently the whole answer.
3. **Python version migration** for apps carrying Python 2 code.
4. **Library resolution** — the OpenSSL case in playbook 6, which appears specifically after
   upgrades because file capabilities or ownership get reset.
5. **Cluster version skew** — peers on mixed versions beyond what the manager supports.
6. **Permissions** after running the upgrade as the wrong user, leaving root-owned files in
   `$SPLUNK_HOME`. Check ownership consistency; this one is invisible in logs but obvious
   once suspected.
