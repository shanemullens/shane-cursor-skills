# Diag anatomy

Where things live and how to read them. Consult this when you need a file the collector
scripts don't cover.

## Contents

- [Directory layout](#directory-layout)
- [Log formats](#log-formats)
- [The files that matter most, by question](#the-files-that-matter-most-by-question)
- [What is missing and why](#what-is-missing-and-why)

## Directory layout

```
diag-<hostname>-<YYYY-MM-DD_HH-MM-SS>/
├── diag.log                  what the collector itself did — read when files are missing
├── manifest.csv              inventory of collected files with sizes
├── systeminfo.txt            uname, ulimits, df, mount, meminfo, cpuinfo, THP, sysctl, SELinux
├── etc/
│   ├── splunk.version        VERSION / BUILD / PRODUCT — establishes what you're dealing with
│   ├── system/{default,local}/*.conf
│   ├── apps/<app>/{default,local}/*.conf
│   ├── users/<user>/<app>/local/*.conf
│   └── licenses/             license stack; presence suggests license manager role
├── log/
│   ├── splunkd.log(.1..N)    the main event log; component-tagged
│   ├── metrics.log(.1..N)    30s interval telemetry: queues, thruput, pipelines, tcpout
│   ├── scheduler.log         saved search dispatch, skips and their reasons
│   ├── audit.log             config changes, logins, search auditing
│   ├── health.log            health report status transitions (9.x+)
│   ├── mongod.log            KVStore engine log
│   ├── python.log            modular input and script errors
│   ├── btool.log             conf parse errors at startup — cheap and very high signal
│   ├── crash-*.log           read in full, always
│   └── introspection/
│       ├── resource_usage.log   per-process and per-host CPU/memory over time
│       └── disk_objects.log     index and volume sizes, bucket counts
├── dispatch/                 search artifacts: info.csv, search.log (often trimmed)
├── kvstore/                  KVStore status and startup logs
├── consensus/                SHC raft state (search head cluster members only)
├── searchpeers/              distributed search peer bundles and status
├── pool/                     search head pooling (legacy)
└── scripts/                  collector helper output
```

Cloud diags and forwarder diags are thinner. A universal forwarder diag has no `dispatch/`,
no `kvstore/`, and a much smaller `metrics.log` — absence there is normal, not a finding.

## Log formats

### splunkd.log

```
07-29-2026 13:22:31.123 +0000 ERROR IndexProcessor [55 indexerPipe] - message text
└── date/time ────────────┘ └tz┘ └lvl┘ └component─┘ └tid subsystem┘   └── body ──┘
```

Multi-line messages (stack traces, config dumps) continue on unprefixed lines — these
are the "unparsed continuation lines" that `log_triage.py` counts and skips.

Components worth knowing:

| Component | Covers |
|---|---|
| `IndexProcessor`, `BucketMover`, `DatabaseDirectoryManager` | indexing, buckets, disk |
| `TcpOutputProc`, `AutoLoadBalancedConnectionStrategy` | forwarding out |
| `TcpInputProc`, `TcpInputConfig` | receiving on 9997 |
| `SearchScheduler`, `SavedSplunker` | scheduled search dispatch |
| `DispatchManager`, `SearchOrchestrator` | search execution |
| `CMMaster`, `CMPeer`, `CMRepJob` | indexer cluster |
| `SHCMaster`, `SHCRaft`, `SHPMaster` | search head cluster |
| `KVStoreConfigurationProvider`, `MongodRunner` | KVStore |
| `SSLCommon`, `HttpListener`, `X509Verify` | TLS |
| `DateParserVerbose`, `AggregatorMiningProcessor`, `LineBreakingProcessor` | parsing |
| `LMTracker`, `LMStackMgr`, `LicenseUsage` | licensing |
| `DeployedServerclass`, `DeployedApplication`, `DC:*` | deployment server/client |
| `WatchdogThread` | main thread stalls — always significant |

### metrics.log

Comma-separated key=value after a `group=` discriminator, emitted every 30 seconds:

```
group=queue, name=parsingqueue, blocked=true, max_size_kb=6144, current_size_kb=6143
group=thruput, name=index_thruput, instantaneous_kbps=812.4, instantaneous_eps=1204
group=per_index_thruput, series="main", kbps=400.0, kb=12000.0
group=per_sourcetype_thruput, series="syslog", kbps=120.5, kb=3600.0
group=pipeline, name=merging, processor=aggregator, cpu_seconds=18.4, executes=982
group=tcpout_connections, name=idx02:9997:idx02, _tcp_KBps=180.2, _tcp_eps=900
group=searchscheduler, dispatched=12, skipped=4, ...
group=mpool, group=map, group=subtask_seconds — internal, usually ignorable
```

`blocked=true` means the queue was full at sample time. One sample is noise; a run of
them is the incident. `max_size_kb` also tells you whether someone has already tuned
queue sizes, which is a strong hint that this problem is recurring.

### scheduler.log

```
07-29-2026 13:00:00.123 +0000 INFO SavedSplunker - savedsearch_id="admin;app;My Search",
  status=skipped, reason="The maximum number of concurrent running jobs for this
  historical scheduled search on this instance has been reached", ...
```

Search on `status=skipped` and group by `reason=`. The reason string is the finding —
concurrency limits, disabled search, missed window, and dispatch failures all look
alike from the user's side but have completely different fixes.

### introspection/resource_usage.log

Two shapes: `component=Hostwide` (whole-host CPU/mem/swap) and `component=PerProcess`
(one line per splunkd/search process with `pct_cpu`, `mem_used`, and often the search ID).
This is how you attribute host-level resource exhaustion to a specific search.

### introspection/disk_objects.log

`component=Indexes` lines carry per-index `total_size`, `total_bucket_count`,
`total_raw_size`. `component=Volumes` carries volume usage. This is where you confirm
whether "the disk is full" is Splunk data or something else on the same mount.

## The files that matter most, by question

| Question | Look here |
|---|---|
| Why is indexing slow or stopped? | `metrics.log` queues → `splunkd.log` IndexProcessor → `systeminfo.txt` df |
| Why are searches skipped? | `scheduler.log` `reason=` → `limits.conf` → `resource_usage.log` |
| Why did it crash? | `crash-*.log` → `splunkd.log` around the crash time → `systeminfo.txt` memory |
| Why won't it start? | `splunkd.log` startup sequence, `btool.log`, `mongod.log` |
| Why is data duplicated? | `inputs.conf` checkpoints, `outputs.conf` cloning, forwarder `splunkd.log` |
| Why is data missing? | `props.conf` timestamp/linebreak, `metrics.log` thruput, license violations |
| Why is the cluster unhealthy? | CM `splunkd.log` CMMaster fixup counts, peer `CMPeer`, `searchpeers/` |
| Is the OS the problem? | `systeminfo.txt` — always check, takes seconds |

## What is missing and why

Diags do not contain: indexed data, `passwd`, private keys, or (by default) anything
excluded via `--exclude`. Since Splunk 8, secrets in conf files are hashed in the diag,
but app-supplied configs sometimes still carry plaintext — `conf_audit.py` flags these
without printing values.

Log retention in a diag defaults to roughly the last week, but that is a *size* budget
as much as a time one. On a busy indexer `metrics.log` can cover only a few hours. Always
report the actual window from `diag_inventory.py` and bound your conclusions to it. If the
customer's incident predates the window, say so and request a new diag or a live search
rather than reasoning past the edge of the data.
