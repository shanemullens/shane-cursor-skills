---
name: splunk-log-generator
description: >-
  Build Python scripts that generate realistic logs for any Splunk sourcetype
  and send them to Splunk via HEC. Supports catalog mode (multi-sourcetype
  registry with CLI selection) and scenario mode (time-sequenced narratives
  with correlated IOCs). Use when generating test data, simulating logs,
  building HEC integrations, populating Splunk indexes, creating demo data,
  or building log simulators for any vendor or product.
---

# Splunk Log Generator

Build Python scripts that generate realistic JSON logs for any Splunk sourcetype and deliver them via HEC.

## Quick Start

1. Gather HEC configuration (URL, token, index)
2. Identify target sourcetypes and their JSON schemas
3. Choose script mode: **Catalog** (volume data) or **Scenario** (narrative demo)
4. Build the script following the architecture in [ARCHITECTURE.md](ARCHITECTURE.md)
5. Validate in Splunk with `--dry-run`, then small batch, then full run

## Prerequisites

- Python 3.8+
- `requests` library (`pip install requests`)
- Splunk HEC token and endpoint URL
- Target index configured in Splunk

## Two Script Modes

Choose the mode based on what the user needs:

### Catalog Mode

For populating dashboards with volume data across multiple sourcetypes.

Structure: `PRODUCT_MAP` registry, `--products` CLI, one generator class per sourcetype inheriting from `BaseGenerator`.

Use when:
- User wants to fill dashboards with realistic data
- Multiple sourcetypes need concurrent generation
- Events are statistically distributed (not story-driven)

### Scenario Mode

For demos, threat hunts, and investigation exercises with a correlated narrative.

Structure: Single `generate_scenario()` function producing time-sequenced events across multiple sourcetypes with shared IOCs.

Use when:
- User wants a specific attack or incident story
- Events must correlate across products (shared IPs, users, hashes)
- Time ordering matters (phase 1 recon, phase 2 exploit, etc.)

## Workflow

Copy and track progress:

```
Task Progress:
- [ ] Phase 1: Gather HEC config and sourcetype requirements
- [ ] Phase 2: Research target sourcetype schemas
- [ ] Phase 3: Build script skeleton (HEC + CLI + mode)
- [ ] Phase 4: Implement generators with realistic field pools
- [ ] Phase 5: Validate in Splunk
```

### Phase 1: Gather Configuration

Ask the user for:

| Setting | Example | Required |
|---------|---------|----------|
| HEC URL | `https://inputs.splunkcloud.com:8088` | Yes |
| HEC Token | (from env var `SPLUNK_HEC_TOKEN`) | Yes |
| Target Index | `main` | Yes |
| SSL Verify | `true` | Yes (default) |
| Sourcetypes | List of target sourcetypes | Yes |
| Event Count | `100` per sourcetype | Yes |
| Time Range | Last 24 hours | Yes |
| Script Mode | Catalog or Scenario | Yes |

**Never hardcode the HEC token.** Always read from environment variables.

### Phase 2: Research Sourcetype Schemas

Determine the JSON schema for each target sourcetype:

1. **Ask the user** if they have sample events or field requirements
2. **Query Splunk via MCP** if available: `index=<idx> sourcetype=<st> | head 5` to inspect existing data
3. **Check vendor documentation** for the product's log format
4. **Inspect Splunk data models** if dashboards use `tstats`: the data model constraints and eval expressions define required field names and values

When no reference exists, ask the user to describe the fields and provide example values.

### Phase 3: Build Script Skeleton

Generate a single Python script. See [ARCHITECTURE.md](ARCHITECTURE.md) for full code.

**Catalog mode structure:**
```python
@dataclass
class HECConfig: ...
class HECClient: ...
class BaseGenerator(ABC): ...
class MySourcetypeGenerator(BaseGenerator): ...
PRODUCT_MAP = {"my-source": MySourcetypeGenerator}
def main(): ...  # argparse with --products, --count, --hours, --dry-run
```

**Scenario mode structure:**
```python
@dataclass
class HECConfig: ...
class HECClient: ...
SHARED_IOCS = {...}  # Attacker IPs, users, hashes
def generate_scenario(start, end) -> list[dict]: ...
def main(): ...  # argparse with --hours, --dry-run
```

### Phase 4: Implement Generators

For each sourcetype:

1. Define `SOURCETYPE` and `SOURCE` class attributes
2. Build field value pools (IPs, users, hostnames, status codes, etc.)
3. Implement `generate()` returning a list of HEC-wrapped events
4. Use `_weighted_choice()` for realistic severity/status distributions
5. Reuse shared pools (`INTERNAL_IPS`, `EXTERNAL_IPS`, `USERS`) across generators for correlation

### Phase 5: Validate in Splunk

1. Run with `--dry-run` to print events to stdout
2. Send a small batch (5-10 events) and verify in Splunk:
   - Correct sourcetype and index
   - Timestamps parse correctly
   - Fields extract properly (check `KV_MODE=json` if needed)
3. If dashboards use `tstats` on data models, verify events land in the correct child nodes
4. Scale up to full event count

## Script Architecture Summary

Full implementation in [ARCHITECTURE.md](ARCHITECTURE.md). Key components:

**HECConfig** -- Dataclass holding URL, token, index, SSL, batch size. Always from env vars.

**HECClient** -- Batch POST to `/services/collector/event` with NDJSON payload. Retries with exponential backoff on 429/errors. Max 1 MB per POST (~50-100 events per batch).

**BaseGenerator** -- Abstract base with:
- Shared identity pools (IPs, users, hostnames, servers, firewalls) for cross-sourcetype correlation
- `_random_ts(start, end)` with business-hour weighting (~70% between 08:00-18:00)
- `_hec_wrap(event, timestamp)` to build the HEC envelope
- ISO timestamp formatters, UUID/hash helpers, `_weighted_choice()`

**CLI** -- `argparse` with `--products`/`--count`/`--hours`/`--dry-run` (catalog) or `--hours`/`--dry-run` (scenario).

## HEC Payload Format

Every event sent to `/services/collector/event`:

```json
{
  "time": 1711234567.123,
  "host": "web-sjc-01",
  "source": "vendor:product:type",
  "sourcetype": "vendor:product:type",
  "index": "my_index",
  "event": { "...product-specific fields..." }
}
```

Batch format is newline-delimited JSON (NOT a JSON array):
```
{"time":1711234567.123,"sourcetype":"my:sourcetype","index":"main","event":{...}}
{"time":1711234568.456,"sourcetype":"my:sourcetype","index":"main","event":{...}}
```

## Realism Guidelines

### Timestamp Distribution
- Spread events across the time range; weight ~70% toward business hours (08:00-18:00 UTC)
- Add sub-second jitter; use epoch with millisecond precision for HEC `time` field
- For scenario mode, order events chronologically within each attack phase

### IP Addresses
- Internal: `10.x.x.x` ranges; keep a consistent pool per run (30+ addresses)
- External/attacker: RFC 5737 documentation ranges (`198.51.100.x`, `203.0.113.x`)
- Same IPs must reappear across sourcetypes for correlation realism

### User Identities
- Email format: `first.last@company.com` (general)
- AD format: `CORP\username` (Windows/AD-integrated products)
- Service accounts: `svc-backup`, `svc-monitoring`, `svc-scanner`
- Reuse the same user pool across all generators

### Severity Distribution
- Default curve: ~60% info/low, ~25% medium, ~10% high, ~5% critical
- Adjust per sourcetype: network devices skew toward info/allow; aggregation products (XDR, SIEM) skew toward medium/high

### Hostnames and Devices
- Pattern: `{function}-{site}-{nn}` (e.g., `fw-sjc-01`, `web-rtp-02`)
- Workstations: `{dept}-ws-{nnn}` (e.g., `eng-ws-042`)
- Keep pools consistent across generators

### Cross-Source Correlation
- In catalog mode, shared class-level pools handle this automatically
- In scenario mode, define a `SHARED_IOCS` dict with attacker IPs/users/hashes that appear across all sourcetypes
- An IP blocked by a firewall should also appear in an XDR alert
- A failed MFA for a user should correspond to a suspicious login elsewhere

## Splunk Compatibility Gotchas

Critical lessons from production iterations. Full details in [LESSONS_LEARNED.md](LESSONS_LEARNED.md).

1. **Reserved field names** -- Never use `tag`, `source`, `host`, `type`, or `punct` as keys in the JSON event body. Splunk treats these as reserved. Use alternatives: `event_tag`, `event_type`, `src_address`.

2. **HEC URL path** -- The client appends `/services/collector/event`. If the user's URL already includes this path, it will double up. Always `rstrip('/')` the base URL and append the endpoint.

3. **Field extraction** -- JSON sent via HEC does not auto-extract fields unless `KV_MODE=json` is set on the sourcetype in `props.conf`. If dashboards show empty panels, this is the likely cause.

4. **Data model alignment** -- If dashboards use `| tstats ... from datamodel=X.Y`, your generator must emit fields and values that satisfy the data model's child node constraints and eval expressions. The field names in the raw JSON must match what the data model evals expect as source fields.

5. **tstats vs raw search** -- `tstats` requires data model acceleration and only works on indexed fields. Search-based data models behave differently from accelerated ones.

6. **Nested JSON and arrays** -- Splunk does not auto-expand nested objects. Dashboards accessing nested fields need `spath` + `mvexpand` in SPL. Prefer flat event structures when possible.

7. **Numeric fields** -- JSON numbers may arrive as strings in Splunk charts. Dashboards may need `tonumber()` wrapping. When possible, emit numbers as actual JSON numbers (not quoted strings).

## Extending an Existing Generator

When importing from another generator script (e.g., reusing `BaseGenerator`, `HECClient`, `HECConfig`):

```python
from existing_generator import BaseGenerator, HECClient, HECConfig
```

Define domain-specific data pools as frozen dataclasses or module-level lists, then build generator classes that inherit `BaseGenerator` and set their own `SOURCETYPE`/`SOURCE`.

## Additional Resources

- [ARCHITECTURE.md](ARCHITECTURE.md) -- Full copy-pasteable code for HECConfig, HECClient, BaseGenerator, CLI patterns, and example generators
- [LESSONS_LEARNED.md](LESSONS_LEARNED.md) -- Detailed gotchas from production iterations covering HEC, field naming, data models, Dashboard Studio, and validation workflows
