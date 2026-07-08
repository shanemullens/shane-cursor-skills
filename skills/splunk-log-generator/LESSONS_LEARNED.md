# Lessons Learned

Hard-won lessons from 12+ production iterations building log generators for Splunk. Each entry traces back to a real bug or multi-hour debugging session. The agent should read this when troubleshooting generator or dashboard issues.

---

## HEC Integration

### Double-Path Bug

**Problem:** User's `SPLUNK_HEC_URL` is `https://inputs.splunkcloud.com:8088/services/collector/event` and the `HECClient` appends `/services/collector/event` again, producing a 404.

**Fix:** Always `rstrip('/')` the base URL before appending the endpoint path. The `HECClient` should own the endpoint path constant (`/services/collector/event`) and expect only the base host+port in the config.

### Batch Size and Payload Limits

**Problem:** Sending 500+ large JSON events in a single POST exceeds the 1 MB HEC payload limit, causing silent drops or 413 errors.

**Fix:** Keep `batch_size` at 50-100 events. For events with large nested structures (behavioral indicators, network IOCs), drop to 25-50.

### PowerShell Environment Variables

**Problem:** On Windows, `export` does not work. Users copy Linux examples and get errors.

**Fix:** Always show both `export` (bash) and `$env:VAR = "value"` (PowerShell) syntax in script docstrings. The agent should detect the user's shell and provide the correct syntax.

### SSL Verification

**Problem:** Splunk Cloud requires SSL verification. Self-signed certs on dev instances fail with certificate errors.

**Fix:** Default `verify_ssl=True`. Only disable with explicit `SPLUNK_VERIFY_SSL=false`. When disabled, suppress the urllib3 InsecureRequestWarning to avoid log noise.

---

## Field Naming Collisions

### `tag` is Reserved

**Problem:** Using `"tag"` as a key in the JSON event body collides with Splunk's built-in `tag` field. The value overwrites Splunk's tag assignments, breaking `tag=` filters in SPL and data model constraints.

**Fix:** Use `"event_tag"` instead. If existing data already uses `"tag"`, backfill with an alias or add the field under a different name and update dashboard SPL.

### `source` Collision

**Problem:** Including `"source"` in the JSON event body can conflict with the HEC metadata `source` field. Splunk may index the wrong value.

**Fix:** Use `"src_address"`, `"event_source"`, or another unambiguous name for source-related fields in the event body. Reserve `source` for the HEC envelope only.

### `type` Ambiguity

**Problem:** Many vendor log formats use `"type"` as an event category field. In Splunk, `type` can collide with internal metadata. Dashboard panels filtering on `type=X` may get unexpected results.

**Fix:** Use `"event_type"` or a product-specific name (e.g., `"alert_type"`, `"flow_type"`). If the real vendor format uses `type`, keep it but be aware of potential search ambiguity.

### `host` in Event Body

**Problem:** Including `"host"` in the JSON body alongside the HEC envelope `host` field causes confusion about which value Splunk indexes.

**Fix:** The HEC envelope `host` is what Splunk uses for the `host` field. If the event body needs a hostname, use `"device"`, `"hostname"`, or `"reporting_host"`.

---

## Data Model Alignment

### Child Node Constraints

**Problem:** Data exists in the base dataset but dashboards using `| tstats ... where nodename=Parent.ChildNode` show empty results.

**Root cause:** Child nodes in Splunk data models have constraints (searches that filter the parent). Events must satisfy both the parent constraint (typically `sourcetype=X`) AND the child constraint (e.g., `EventType="Connection Event"`).

**Fix:** Read the data model JSON or use `| datamodel ModelName ChildNode search` to discover the exact constraint. Ensure the generator emits the required field with the exact expected value.

### Eval Source Field Names

**Problem:** Data model eval expressions transform raw field names into display names. Example: `eval initiator_ip = src_ip`. The generator emits `initiator_ip` directly, but `tstats` looks for the pre-eval name.

**Root cause:** `tstats` operates on the data model's calculated fields, which are the *output* of eval expressions. But the eval *input* fields must exist in the raw event for the eval to produce output.

**Fix:** Emit the **source field names** that the data model evals expect as input (e.g., `src_ip`), not the output field names (e.g., `initiator_ip`). The data model's eval will produce the output fields automatically.

### tstats vs Raw Search

**Problem:** `tstats` returns results but raw `index=X sourcetype=Y` searches show different field names or values.

**Root cause:** `tstats` queries accelerated data model fields (post-eval), while raw searches show the original JSON fields. These can differ when evals rename or transform fields.

**Fix:** Understand which query the dashboard uses. If `tstats`, align to the data model eval inputs. If raw search, align to the literal JSON field names.

### Search-Based Data Models

**Problem:** Some data models are search-based (not accelerated). `tstats` returns no results even though data exists.

**Fix:** Search-based data models use `| datamodel ... search` instead of `| tstats`. The generator must emit fields that match the base search constraints. If the dashboard uses `tstats`, the data model must be accelerated in Splunk.

---

## JSON Field Extraction

### KV_MODE=json Requirement

**Problem:** JSON events sent via HEC appear in Splunk as raw text. Individual fields are not searchable, and dashboards show empty panels.

**Root cause:** By default, Splunk does not auto-extract JSON fields from HEC payloads unless the sourcetype has `KV_MODE=json` configured in `props.conf`.

**Fix:** Ensure the target sourcetype has `KV_MODE=json` set. This is a Splunk-side configuration, not a generator issue. If the generator creates a new sourcetype, document that `props.conf` must include:

```
[my:sourcetype]
KV_MODE = json
TIME_FORMAT = %s.%3N
```

### Nested JSON Paths

**Problem:** Event contains `{"analysis": {"threat_score": 85}}` but the dashboard queries `analysis.threat_score` and gets no results.

**Root cause:** Splunk does not auto-expand nested JSON objects into dot-separated field names unless `spath` is used in the search.

**Fix:** Prefer flat event structures when possible. If nesting is required (to match vendor format), the dashboard SPL must use `| spath` to extract nested fields, or use `| spath input=_raw path=analysis.threat_score output=threat_score`.

### Array Fields

**Problem:** Event contains `{"tactics": ["initial-access", "execution"]}` but dashboard shows `tactics=["initial-access", "execution"]` as a single string.

**Fix:** Splunk treats JSON arrays as multivalue fields only when extracted with `spath` + `mvexpand`. Dashboard SPL must include:

```spl
| spath input=_raw path=tactics{} output=tactic
| mvexpand tactic
```

When designing generators, prefer flat structures. If arrays are needed, document the required SPL extraction.

### Numeric Fields as Strings

**Problem:** Dashboard chart shows `threat_score` on Y-axis but the chart is empty or shows "N/A".

**Root cause:** JSON numbers sent via HEC may arrive as string values in Splunk, depending on extraction configuration. Chart visualizations require numeric types.

**Fix:** Emit numbers as actual JSON numbers (not quoted strings) in the generator. In dashboard SPL, wrap with `| eval threat_score=tonumber(threat_score)` as a safety net.

---

## Dashboard Studio Compatibility

### fontSize Must Be a String

**Problem:** Dashboard Studio JSON definition includes `"fontSize": 24` (integer) and the viz renders with default font size.

**Fix:** Always use string values: `"fontSize": "24"`. Dashboard Studio's JSON schema requires string type for font sizes.

### trendDisplay Valid Enums

**Problem:** Using `"trendDisplay": "sparkline"` in a single value visualization causes it to silently fall back to default.

**Fix:** Valid values are `"percent"`, `"absolute"`, or `"off"` only. There is no `"sparkline"` option for `trendDisplay`.

### Absolute Layout Positioning

**Problem:** Visualizations overlap or render off-screen in Dashboard Studio with absolute layout.

**Fix:** When using absolute layout, specify explicit `x`, `y`, `width`, `height` for every visualization. Test at standard viewport widths (1280, 1920). Use `"type": "block"` layout when precise positioning is not required.

---

## Validation Workflow

### Generate-Query-Fix Loop

The most reliable validation pattern across all iterations:

1. **Generate** a small batch (5-10 events) with `--dry-run` to inspect JSON
2. **Send** the small batch to Splunk
3. **Query via MCP** (or Splunk UI): `index=<idx> sourcetype=<st> | head 5 | fields *`
4. **Compare** actual field names and values against dashboard expectations
5. **Fix** the generator (not the data model) and repeat

Prefer generator-only fixes over data model edits. Data models are shared infrastructure; generator scripts are disposable.

### MCP Validation Queries

Useful queries when validating generator output:

```spl
# Check events arrived
index=<idx> sourcetype=<st> earliest=-1h | stats count

# Inspect field names
index=<idx> sourcetype=<st> earliest=-1h | head 1 | fields *

# Verify data model child node population
| tstats count from datamodel=MyModel.MyDataset where nodename=MyDataset.ChildNode

# Check field values
index=<idx> sourcetype=<st> earliest=-1h | stats values(event_type) as types

# Inspect sourcetype config
| rest /servicesNS/-/-/configs/conf-props | search title="my:sourcetype"
```

### Common Validation Failures

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Events not in Splunk | Wrong HEC URL, expired token, wrong index | Check HEC config, verify token permissions |
| Fields not extracted | Missing `KV_MODE=json` | Configure `props.conf` for the sourcetype |
| Data model panels empty | Child node constraint not satisfied | Check required field values in data model |
| Dashboard charts empty | Numeric fields as strings | Add `tonumber()` in SPL or emit as JSON numbers |
| Wrong sourcetype | `source` vs `sourcetype` confusion in HEC | Verify both `source` and `sourcetype` in HEC envelope |
| Duplicate/missing fields | JSON body key collides with HEC metadata | Rename body keys (`tag` -> `event_tag`, etc.) |

---

## Cross-Source Correlation

### Shared IOC Pattern (Scenario Mode)

Define all shared indicators at the top of the script:

```python
ATTACKER_IP = "203.0.113.99"
TARGET_USER = "john.smith@company.com"
COMPROMISED_HOST = "eng-ws-042"
MALWARE_HASH = "7d865e959b2466918c9863afca942d0fb89d7c9ac0c99bafc3749504ded97730"
C2_DOMAIN = "evil.example.com"
```

Every sourcetype generator references these same values, enabling cross-product correlation in Splunk using `src_ip`, `user`, `sha256`, etc.

### Correlation ID Pattern

For multi-event sequences within a single sourcetype:

```python
correlation_id = str(uuid.uuid4())
```

Include `correlation_id` (or `incident_id`, `session_id`, etc.) in every related event. This enables `transaction` or `stats ... by correlation_id` queries in Splunk.

### Background Noise

Realistic scenarios need legitimate traffic alongside malicious indicators:

- Generate 5-10x more benign events than attack events per phase
- Use different (non-IOC) users and IPs for background noise
- Vary severity: background events should be mostly info/low
