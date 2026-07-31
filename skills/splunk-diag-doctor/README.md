# splunk-diag-doctor

Root-cause a Splunk deployment from diag files. Drop a diag (folder or `.tar.gz`) into the
repo and ask; the skill inventories it, collects evidence, correlates, and writes an
evidence-backed report with ready-to-apply remediation.

## Install

**Cursor** — copy into the project or your global rules directory:

```bash
cp -r splunk-diag-doctor /path/to/repo/.cursor/skills/
```

**Claude Code** — same layout:

```bash
cp -r splunk-diag-doctor ~/.claude/skills/
```

No dependencies. All scripts are stdlib Python 3.

## Use

Put the diag anywhere in the repo, then:

- *"Triage the diag in this repo"* — open sweep
- *"This indexer has been lagging since Tuesday afternoon, check the diag"* — symptom-driven
- *"Compare these three peer diags and tell me why the cluster won't reach RF"* — multi-diag

Reports land in `diag-analysis/<hostname>-<date>.md`.

## Scripts

Run standalone if you want raw output. All accept `--json`.

| Script | Purpose |
|---|---|
| `diag_inventory.py --root .` | Find diags, extract tarballs (`--extract`), identify host/version/roles/log window |
| `system_check.py --diag X` | ulimits, THP, disk, memory, CPU, SELinux from `systeminfo.txt` |
| `log_triage.py --diag X` | Cluster `splunkd.log` messages into patterns with counts and time ranges; summarize crash logs |
| `metrics_analyze.py --diag X` | Queue blocking and fill, throughput, tcpout, pipeline CPU, top sourcetypes |
| `conf_audit.py --diag X` | Known-bad conf patterns, precedence conflicts, plaintext secret detection |

## Extending

The conf rules are a plain list in `scripts/conf_audit.py` — append a tuple of
`(conf, stanza_regex, key, predicate, severity, message)` when you meet a new failure mode.
The `message` goes straight into the report, so write it as advice.

`references/root-cause-playbooks.md` is the diagnostic knowledge base. Adding a playbook
section is usually more valuable than adding a rule, since it teaches the reasoning rather
than a single check.

## Design notes

- Diags are large. The scripts aggregate so that only findings reach the model's context;
  raw log reads are always bounded.
- Diags are treated as read-only evidence — nothing is written back into them.
- Diags contain customer identifiers and occasionally credential material. `conf_audit.py`
  reports the location of suspected plaintext secrets and never prints the values.
