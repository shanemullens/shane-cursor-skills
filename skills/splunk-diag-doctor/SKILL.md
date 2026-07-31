---
name: splunk-diag-doctor
description: Root-cause a Splunk deployment from diag files. Crawls one or many Splunk diags (extracted folders or .tar.gz) sitting in the repo, correlates splunkd.log, metrics.log, systeminfo.txt, and the conf layer into an evidence-backed root cause, then writes a remediation plan with ready-to-apply conf stanzas and CLI. Use this skill whenever a Splunk diag is present or mentioned, whenever the user uploads or points at a `diag-*` folder or tarball, and whenever they describe a Splunk problem — indexing lag, blocked queues, skipped searches, crashes, KVStore or mongod failures, SSL/cert errors, cluster bucket fixup, replication factor not met, license violations, forwarder connection failures, high CPU or memory, disk pressure, duplicate or missing events — and expect the answer to come from diag data rather than a live search. Also use it for "why is this indexer slow", "what's wrong with this search head", "review this diag", "triage this support case bundle", or any request to compare diags across a cluster.
---

# Splunk Diag Doctor

A diag is a **frozen snapshot of one instance**, usually captured after the fact by someone who
was not watching the failure happen. That shapes everything about how to read it:

- **The loudest error is rarely the root cause.** Splunk fails backwards. A blocked `indexqueue`
  reports itself long before the slow disk or dead peer that caused it. Always trace upstream to
  downstream, then invert.
- **A diag is bounded in time.** Default collection is the last ~7 days of logs, and `metrics.log`
  rotates fast on a busy instance — often only a few hours survive. Check your window before
  concluding "this never happened."
- **Absence of evidence is common and worth saying out loud.** Diags are frequently collected with
  `--exclude` filters, from the wrong instance, or after a restart wiped the symptom. A findings
  report that admits what it could not determine is far more useful to a customer than one that
  invents a confident story.

Never assert a root cause you cannot point at a file and line for. Every finding in the report
carries its evidence. Where the evidence supports two or more explanations, say so and give the
discriminating test.

## Phase 0 — Inventory before you read anything

Do not start grepping. Establish what you actually have first, because the instance's **role**
determines which failure modes are even possible and which logs matter.

```bash
python3 scripts/diag_inventory.py --root . --json
```

This finds every diag under the repo (extracted directories and `.tar.gz`/`.tgz` archives),
extracts archives into `.diag-work/` when needed, and reports per diag: hostname, Splunk version
and build, OS, detected roles, log time window, and diag capture time.

Read the output and state back to the user what you found — "three diags: one cluster manager and
two indexer peers, all 9.4.1, captured within four minutes of each other" — before analyzing. If
the inventory disagrees with what the user believes they gave you (wrong host, forwarder instead
of indexer, a diag from six months ago), stop and raise it. Analyzing the wrong diag carefully is
worse than analyzing nothing.

**Role determines the reading order:**

| Role | Read first | Read second |
|---|---|---|
| Indexer / peer | `metrics.log` queues, `disk_objects.log` | `splunkd.log` IndexProcessor, clustering |
| Search head | `scheduler.log` skips, dispatch dir size | `splunkd.log` SearchScheduler, KVStore |
| SHC member | `splunkd.log` SHCMaster/SHCRaft, `consensus/` | KVStore replication |
| Cluster manager | `splunkd.log` CMMaster, bucket fixup counts | peer connectivity |
| Heavy forwarder | `metrics.log` tcpout + queues | props/transforms cost in `group=pipeline` |
| Universal forwarder | `splunkd.log` TcpOutputProc, `metrics.log` thruput | inputs.conf, checkpoints |
| Deployment server | `splunkd.log` DS/DC handlers, client count | serverclass.conf size |

## Phase 1 — Frame the question

**If the user gave a symptom, that is the hypothesis to test.** Go straight to the matching
playbook in `references/root-cause-playbooks.md`, gather the evidence it names, and try hard to
*falsify* it before accepting it. Confirmation bias is the main failure mode here: a busy Splunk
instance always has enough warnings lying around to "support" whatever theory you started with.

**If the user gave no symptom, run the sweep** — all four collectors below, ranked by severity.
Report the top findings rather than an exhaustive dump; a 200-item list of every WARN in
`splunkd.log` is noise, not analysis.

## Phase 2 — Collect evidence

Run these against each diag. They are stdlib-only Python, no install step. Each takes
`--diag <path>` and supports `--json` for machine-readable output you can correlate across diags.

```bash
python3 scripts/system_check.py   --diag <diag>   # ulimits, THP, disk, memory, CPU, SELinux
python3 scripts/log_triage.py     --diag <diag>   # splunkd.log error/warn clustering + crashes
python3 scripts/metrics_analyze.py --diag <diag>  # queue fill, blocking, thruput, tcpout, pipeline cost
python3 scripts/conf_audit.py     --diag <diag>   # known-bad conf patterns and precedence conflicts
```

`system_check.py` is cheap and catches an outsized share of real problems — ulimits and transparent
huge pages alone explain a large fraction of "Splunk is mysteriously slow" cases. Run it always,
even when the user's symptom sounds purely application-level.

`log_triage.py` clusters messages into patterns rather than listing lines, so 40,000 repetitions of
one error collapse to a single row with a count and a first/last timestamp. **The count and the time
distribution matter more than the text** — an error that fired 3 times last Tuesday is background
noise; the same error firing 900 times an hour starting at 14:02 is your incident.

When you need something the scripts do not cover, grep directly. `references/diag-anatomy.md` maps
the whole diag layout — which file holds what, and the log formats you will be parsing.

## Phase 3 — Correlate

**Within a diag**, build a timeline. Line up the first occurrence of each candidate cause against
the onset of the symptom. Causes precede effects; anything that started *after* the symptom is a
consequence, not a cause. This one discipline resolves most ambiguous cases.

**Across diags** (when the inventory found more than one), the questions are different and usually
more decisive:

- Is the finding **on every instance or just one?** Universal → configuration, version, or an
  upstream dependency. Isolated → that host's disk, network, or resources.
- Do the **timelines align?** Simultaneous onset across peers points at a shared dependency: the
  cluster manager, a license manager, DNS, NTP, a storage array, a network change.
- Do the **conf files agree?** Compare `conf_audit.py --json` output between peers. Config drift
  between cluster members is a common and easily-missed root cause.
- For clusters, is the **cluster manager's** view consistent with the peers' view? Disagreement
  about generation or bucket state is itself the finding.

## Phase 4 — Write the report

Write to `diag-analysis/<hostname>-<YYYY-MM-DD>.md` (or `<cluster-label>-<date>.md` for a
multi-diag analysis). Create the directory if needed. Use this structure:

```markdown
# Splunk Diag Analysis — <hostname> (<role>, <version>)

**Diag captured:** <timestamp>  **Log window:** <first> → <last>  **Analyzed:** <date>

## Verdict
<Two or three sentences. The root cause, the confidence level, and the single most
important action. A reader who stops here should still know what to do.>

## Root cause
<What is actually wrong and the mechanism by which it produces the observed symptom.
If multiple explanations remain live, list them with the test that discriminates.>

## Evidence
| # | Finding | Severity | Source |
|---|---|---|---|
| 1 | <what was observed> | Critical | `log/splunkd.log:14882` |

## Remediation
### Immediate
### Short term
### Preventive

## Secondary findings
<Real but not causal. Worth fixing, clearly separated so they don't muddy the verdict.>

## Not determinable from this diag
<What you'd need: a live search, a longer window, a diag from another instance, an OS-level check.>
```

**Severity means impact, not log level.** A single `ERROR` about an expired certificate outranks
ten thousand `WARN`s about a noisy sourcetype. Rank by what it does to the deployment: Critical
(data loss, outage, imminent), High (degraded, will escalate), Medium (inefficiency, risk),
Low (hygiene).

### Remediation must be applicable, not aspirational

Give the actual stanza with the actual file path and the actual restart requirement. Not "tune the
queue sizes" but:

```ini
# $SPLUNK_HOME/etc/system/local/server.conf  — requires splunkd restart
[queue=parsingQueue]
maxSize = 6MB
```

`references/remediation-snippets.md` has vetted stanzas and CLI for the common fixes. Pull from it
rather than composing from memory — the defaults, units, and restart semantics are easy to get
subtly wrong, and a wrong stanza handed to a customer is worse than no stanza.

Always state: the file path including scope (`system/local` vs an app), whether it needs a restart
or a reload, and what to check afterward to confirm the fix landed. Where a change carries risk
(anything touching `limits.conf`, queue sizing, or indexer cluster settings), say what the risk is.
Do not silently edit conf files inside the diag — a diag is evidence, and mutating it destroys the
ability to re-examine.

## Handling scale

Real diags are hundreds of MB. Do not read log files into context wholesale — the scripts exist so
that only aggregated findings and targeted excerpts reach you. When you do need raw lines, bound
the read: `grep -n 'pattern' log/splunkd.log | head -50`, or pull a specific line range around an
event you already located. Reading a 2 GB `metrics.log` directly will exhaust context and produce
worse analysis than the summary would have.

## A note on sensitivity

Diags carry customer hostnames, internal IPs, usernames, index names, and occasionally secrets in
conf files — `sslPassword`, `pass4SymmKey`, `bindDNpassword`, tokens in app configs. These are
hashed in modern versions but not always. If the report is going to a customer or into a ticket,
flag anything sensitive you noticed and offer to redact identifiers. Never paste credential
material into the report, even redacted-looking, and never include it in a summary.

## Reference files

- `references/diag-anatomy.md` — diag layout, what lives where, log formats and how to parse them.
  Read when you need a file the scripts do not cover.
- `references/root-cause-playbooks.md` — symptom → evidence → root cause → fix, for the recurring
  failure classes. **Read the matching playbook whenever the user names a symptom.**
- `references/remediation-snippets.md` — vetted conf stanzas and CLI for the standard fixes.
  Read before writing any remediation section.
- `examples/sample-report.md` — a worked report showing the expected depth, how evidence is
  cited, and how a live alternative explanation is presented rather than papered over.
