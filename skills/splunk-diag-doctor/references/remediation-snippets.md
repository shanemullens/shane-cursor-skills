# Remediation snippets

Vetted stanzas and commands for the common fixes. Pull from here rather than composing from
memory — units, defaults, and restart semantics are easy to get subtly wrong, and a wrong
stanza handed to a customer is worse than no stanza.

Every entry states the **file and scope**, the **restart requirement**, and a **verification
step**. Include all three in the report. A remediation the customer can't confirm landed is
half a remediation.

## Contents

- [OS-level](#os-level)
- [Indexing and pipeline](#indexing-and-pipeline)
- [Forwarding](#forwarding)
- [Search concurrency](#search-concurrency)
- [Parsing](#parsing)
- [KVStore](#kvstore)
- [Certificates](#certificates)
- [Cluster](#cluster)
- [Verification commands](#verification-commands)

---

## OS-level

### ulimits

The setting must apply to the account that runs splunkd, and how you set it depends on how
Splunk is started. Setting only `limits.conf` and starting via systemd is the usual reason
"we already fixed the ulimits" turns out to be false.

**systemd-managed (modern default):**

```ini
# /etc/systemd/system/Splunkd.service.d/override.conf
[Service]
LimitNOFILE=64000
LimitNPROC=16000
LimitFSIZE=infinity
LimitDATA=infinity
```
```bash
systemctl daemon-reload && systemctl restart Splunkd
```

**init/manual start:**

```ini
# /etc/security/limits.d/99-splunk.conf
splunk  hard  nofile  64000
splunk  soft  nofile  64000
splunk  hard  nproc   16000
splunk  soft  nproc   16000
splunk  hard  fsize   unlimited
splunk  soft  fsize   unlimited
```

**Verify (must be run as the splunk user, and after a full restart):**
```bash
su - splunk -c 'ulimit -n -u -f'
# or, authoritatively, against the running process:
cat /proc/$(pgrep -f 'splunkd.*-p .* start' | head -1)/limits
```
The `/proc` check is the one that matters — it reports what the process actually got.

### Transparent huge pages

```bash
echo never > /sys/kernel/mm/transparent_hugepage/enabled
echo never > /sys/kernel/mm/transparent_hugepage/defrag
```

Not persistent. Make it survive reboot with a systemd unit or the kernel command line
(`transparent_hugepage=never` in GRUB). Splunk must be restarted afterward to allocate
without THP.

**Verify:** `cat /sys/kernel/mm/transparent_hugepage/enabled` → `always madvise [never]`

### vm.max_map_count

```bash
sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' >> /etc/sysctl.d/99-splunk.conf
```

---

## Indexing and pipeline

### Free disk before indexing halts

`minFreeSpace` is the floor at which Splunk stops indexing. Raising it does not create
space — it only moves the threshold. The real fix is space or retention.

```ini
# $SPLUNK_HOME/etc/system/local/server.conf  — restart required
[diskUsage]
minFreeSpace = 5000
```

Retention, per index:

```ini
# $SPLUNK_HOME/etc/system/local/indexes.conf  — restart required
[myindex]
maxTotalDataSizeMB = 500000
frozenTimePeriodInSecs = 7776000
```

`maxTotalDataSizeMB` is per index and covers hot+warm+cold. `frozenTimePeriodInSecs` is age
based. Whichever triggers first wins, so set both deliberately rather than leaving one at
its very large default.

### Parallel ingestion pipelines

Only helps when CPU is available and the bottleneck is pipeline throughput, not disk.
Doubling this on a disk-bound indexer makes things worse.

```ini
# $SPLUNK_HOME/etc/system/local/server.conf  — restart required
[general]
parallelIngestionPipelines = 2
```

Requires headroom: roughly 2 cores and 1 GB RAM per additional pipeline.

### Queue sizing

A last resort for burst absorption, never a fix for a sustained bottleneck.

```ini
# $SPLUNK_HOME/etc/system/local/server.conf  — restart required
[queue=parsingQueue]
maxSize = 6MB
```

Say explicitly in the report that this buffers rather than fixes, and name what it is
buffering against.

---

## Forwarding

### Remove the throughput throttle

```ini
# $SPLUNK_HOME/etc/system/local/limits.conf on the forwarder  — restart required
[thruput]
maxKBps = 0
```

`0` means unlimited. The universal forwarder default is 256 KB/s, deliberately, to protect
the monitored host. Removing it is right for forwarders expected to move real volume and
wrong for latency-sensitive production hosts where Splunk should stay out of the way. State
which case applies.

### Load balancing

```ini
# $SPLUNK_HOME/etc/system/local/outputs.conf  — restart required
[tcpout:primary_indexers]
server = idx01:9997, idx02:9997, idx03:9997
autoLBFrequency = 30
autoLBVolume = 0
useACK = false
```

`autoLBFrequency = 30` is the default and appropriate for most deployments. Raising it pins
forwarders to indexers for longer and skews load.

### Indexer acknowledgement

```ini
[tcpout:primary_indexers]
useACK = true
```

Turn on only where end-to-end delivery guarantees are required. Budget roughly 3× the output
queue memory and expect it to propagate indexer slowness back to the forwarder as blocking.

---

## Search concurrency

Total concurrent searches = `base_max_searches` + (`max_searches_per_cpu` × cores).

```ini
# $SPLUNK_HOME/etc/system/local/limits.conf  — restart required
[search]
base_max_searches = 6
max_searches_per_cpu = 1

[scheduler]
max_searches_perc = 50
```

Raising these does not create capacity. If skips coincide with high CPU, raising limits
converts skipped searches into a slow, unusable instance — worse for the user. Say so when
recommending against it.

### Dispatch cleanup

```ini
# $SPLUNK_HOME/etc/system/local/limits.conf  — restart required
[search]
ttl = 600
remote_ttl = 600
```

Per saved search:

```ini
# savedsearches.conf  — reload via debug/refresh or restart
[My Search]
dispatch.ttl = 2p
```

Existing artifacts are not removed by a TTL change. Clean up separately and confirm the
count under `$SPLUNK_HOME/var/run/splunk/dispatch` drops.

---

## Parsing

The single largest indexing performance win available on most deployments is turning off
line merging for high-volume sourcetypes and defining an explicit line breaker.

```ini
# props.conf on indexers and heavy forwarders  — restart required
[my_sourcetype]
SHOULD_LINEMERGE = false
LINE_BREAKER = ([\r\n]+)
TIME_PREFIX = ^
TIME_FORMAT = %Y-%m-%dT%H:%M:%S.%3N%z
MAX_TIMESTAMP_LOOKAHEAD = 32
TRUNCATE = 10000
TZ = UTC
```

Notes that matter:
- `LINE_BREAKER` is a regex whose **first capturing group** is what gets discarded between
  events. `([\r\n]+)` is the one-event-per-line case.
- `TIME_PREFIX` and `MAX_TIMESTAMP_LOOKAHEAD` together are what make timestamp extraction
  cheap. Without them Splunk scans further than it needs to on every event.
- These are index-time settings. They apply to **newly indexed data only** — existing events
  are not reparsed. Set expectations accordingly.
- They belong wherever parsing happens: indexers, or heavy forwarders if parsing there.

---

## KVStore

### Storage engine migration

```bash
$SPLUNK_HOME/bin/splunk stop
$SPLUNK_HOME/bin/splunk migrate migrate-kvstore
$SPLUNK_HOME/bin/splunk start
```

Back up first (`$SPLUNK_HOME/var/lib/splunk/kvstore`) and expect downtime proportional to
collection size. On a search head cluster this is a coordinated operation across members,
not a per-member action.

### Status and repair

```bash
$SPLUNK_HOME/bin/splunk show kvstore-status
$SPLUNK_HOME/bin/splunk clean kvstore --local     # destructive: wipes local KVStore data
```

`clean kvstore` destroys data. On an SHC member it can be legitimate because the data
re-replicates from other members; on a standalone search head it is data loss. Never
recommend it without naming that distinction.

---

## Certificates

### Check expiry before anything else

```bash
openssl x509 -enddate -noout -in $SPLUNK_HOME/etc/auth/server.pem
openssl x509 -enddate -noout -in $SPLUNK_HOME/etc/auth/ca.pem
```

### Regenerate default internal certs

```bash
$SPLUNK_HOME/bin/splunk stop
mv $SPLUNK_HOME/etc/auth/server.pem $SPLUNK_HOME/etc/auth/server.pem.bak
$SPLUNK_HOME/bin/splunk start   # regenerates on startup
```

This regenerates *default* self-signed certs. If the deployment uses custom CA-signed certs,
this is the wrong action and will break trust relationships — check `server.conf`
`[sslConfig]` and `inputs.conf`/`outputs.conf` for custom `serverCert` paths first.

### OpenSSL library resolution

When `splunkd` binds the system libcrypto instead of its own:

```bash
# Confirm what it is actually loading
ldd $SPLUNK_HOME/bin/splunkd | grep -E 'libcrypto|libssl'

# Check for the usual culprits: file capabilities or setuid bits force glibc
# secure-execution mode, which drops $ORIGIN/RPATH resolution
getcap $SPLUNK_HOME/bin/splunkd
ls -l $SPLUNK_HOME/bin/splunkd
```

If capabilities are set, removing them (`setcap -r`) restores normal library resolution —
but they were probably set to allow binding privileged ports or reading protected logs.
Solve that need another way (systemd `AmbientCapabilities`, or a higher port with a
redirect) rather than simply stripping them and breaking the input.

---

## Cluster

### Health and fixup state

```bash
$SPLUNK_HOME/bin/splunk show cluster-status --verbose
$SPLUNK_HOME/bin/splunk list cluster-peers
$SPLUNK_HOME/bin/splunk list excess-buckets
```

### Rolling restart

```bash
$SPLUNK_HOME/bin/splunk rolling-restart cluster-peers
```

Only when the cluster is otherwise healthy. Rolling-restarting a cluster that is mid-fixup
extends the fixup and can push it further from RF/SF compliance.

### Maintenance mode

```bash
$SPLUNK_HOME/bin/splunk enable maintenance-mode
# ... work ...
$SPLUNK_HOME/bin/splunk disable maintenance-mode
```

Suppresses fixup during planned peer downtime. Leaving it enabled by accident is a
silent way to run without your configured replication factor, so pair every enable
recommendation with an explicit reminder to disable.

---

## Verification commands

Give the customer the check, not just the change.

```bash
# What is the effective config, and which file won?
$SPLUNK_HOME/bin/splunk btool <conf> list --debug <stanza>

# Confirm conf parse errors are gone
$SPLUNK_HOME/bin/splunk btool check

# Live queue state (the same data metrics.log records)
index=_internal source=*metrics.log group=queue
| stats max(eval(current_size_kb/max_size_kb*100)) as max_fill by name

# Skipped searches by reason
index=_internal source=*scheduler.log status=skipped
| stats count by reason

# Confirm ulimits on the running process
cat /proc/$(pgrep -f 'splunkd.*start' | head -1)/limits
```

`btool ... --debug` is the answer to almost every "which setting is actually in effect"
question, and it belongs in any remediation that touches a conf file with a precedence
conflict.
