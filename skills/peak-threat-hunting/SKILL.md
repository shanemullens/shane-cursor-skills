---
name: peak-threat-hunting
description: Conduct threat hunts in Splunk using the PEAK framework (Prepare, Execute, Act with Knowledge). Supports hypothesis-driven, baseline, and model-assisted hunts. Use when the user wants to threat hunt, investigate security anomalies, baseline data sources, detect adversary techniques, or map findings to MITRE ATT&CK.
---

# PEAK Threat Hunting in Splunk

Guide threat hunts using the PEAK framework, executing SPL queries via the Splunk MCP server.

## Quick Start

When a user requests a threat hunt:

1. **Identify hunt type** based on their goal:
   - **Hypothesis-driven**: Hunting specific adversary behavior (e.g., "Hunt for DNS tunneling")
   - **Baseline**: Understanding normal to find anomalies (e.g., "Baseline our firewall logs")
   - **Model-Assisted (M-ATH)**: Using ML/statistical models (e.g., "Find anomalous login patterns")

2. **Follow the PEAK phases**: Prepare → Execute → Act

3. **Run SPL queries** using the Splunk MCP server's `run_splunk_query` tool

4. **Track progress** using the hunt checklist for the selected type

## Hunt Type Selection

```
Is this topic-based or data-based?
├── Topic-based (specific behavior/threat) → Does it have implicit complexity?
│   ├── Yes (many variables, ML needed) → Model-Assisted Hunt
│   └── No (explicit detection logic) → Hypothesis-Driven Hunt
└── Data-based (understand a data source) → Baseline Hunt
```

---

## Hypothesis-Driven Hunt

Use when hunting for specific adversary behaviors or techniques.

### Phase 1: Prepare

```
Hunt Preparation Checklist:
- [ ] Topic selected and scoped
- [ ] Research completed (TTPs, threat intel)
- [ ] Hypothesis generated (testable statement)
- [ ] ABLE framework applied
- [ ] Data sources identified
- [ ] Hunt plan created
```

**1. Select Topic**: Identify the behavior to hunt (e.g., "lateral movement", "credential theft")

**2. Research Topic**: Gather threat intelligence:
- Known techniques for implementing this tactic
- Existing detections and gaps
- Threat actor TTPs (check MITRE ATT&CK)
- Prior hunts on this topic

**3. Generate Hypothesis**: Create a testable, falsifiable statement:
```
Template: "[Actor] may be [behavior] in [location] using [technique]"
Example: "An adversary may be exfiltrating data via DNS tunneling from finance endpoints"
```

**4. Apply ABLE Framework** to scope the hunt:

| Component | Question | Example |
|-----------|----------|---------|
| **A**ctor | Who/what threat? | APT group, insider, malware family |
| **B**ehavior | What TTP? | DNS tunneling, credential dumping |
| **L**ocation | Where to look? | Finance endpoints, DMZ servers |
| **E**vidence | What data/indicators? | DNS logs, unusually long queries |

**5. Check Data Availability**: Query available indexes and data:

```
Action: Run via Splunk MCP
Tool: get_indexes
Purpose: Identify available data sources
```

```
Action: Run via Splunk MCP
Tool: run_splunk_query
Query: | tstats count WHERE index=* by index, sourcetype | sort -count
Purpose: See data volume by sourcetype
```

### Phase 2: Execute

```
Hunt Execution Checklist:
- [ ] Data gathered and filtered
- [ ] Data pre-processed if needed
- [ ] Analysis techniques applied
- [ ] Hypothesis refined (if needed)
- [ ] Critical findings escalated
```

**1. Gather Data**: Collect evidence based on ABLE scope

**2. Pre-Process Data**: Ensure data quality:
- Normalize timestamps to UTC
- Filter to relevant scope
- Handle missing values

**3. Analyze**: Apply hunting techniques:

| Technique | When to Use | SPL Pattern |
|-----------|-------------|-------------|
| Stack counting (LFO) | Find rare values | `| stats count by field | sort count` |
| Frequency analysis | Find unusual patterns | `| timechart count by field` |
| Clustering | Group similar events | `| cluster field=field_name` |
| Outlier detection | Find statistical anomalies | `| eventstats avg(x) stdev(x) | eval z=(x-avg)/stdev` |

**4. Refine Hypothesis**: If initial analysis is inconclusive, adjust scope or indicators

**5. Escalate Critical Findings**: Immediately escalate confirmed malicious activity

### Phase 3: Act

```
Hunt Completion Checklist:
- [ ] Hunt preserved (queries, data, findings)
- [ ] Findings documented
- [ ] Detections created/updated
- [ ] Dashboard created (if applicable)
- [ ] New hunt ideas logged
- [ ] Findings communicated to stakeholders
```

**1. Preserve Hunt**: Save queries, screenshots, and methodology

**2. Document Findings**: Use template in [HUNT_TEMPLATES.md](HUNT_TEMPLATES.md)

**3. Create Detections**: Convert findings to automated detection (see Detection Hierarchy below)

**4. Create Dashboard**: If the hunt produced findings that warrant ongoing monitoring or analyst review (Detection Hierarchy Level 2), invoke the `splunk-dashboard-studio` skill. Pass it:
- All SPL queries used during the Execute phase (both successful and refined versions)
- The hunt hypothesis and ABLE scope (Actor, Behavior, Location, Evidence)
- Key findings: field names, notable values, thresholds discovered
- The time range used during the hunt
- Any severity classifications or risk scores identified
- Context about the target audience (SOC analysts, hunt team, management)

The subagent will design the layout, select appropriate visualizations, assemble valid Simple XML, and optionally deploy and test the dashboard on the Splunk instance.

**5. Communicate**: Share with SOC, IR, detection engineering teams

---

## Baseline Hunt

Use when establishing normal behavior for a data source to identify anomalies.

### Phase 1: Prepare

```
Baseline Preparation Checklist:
- [ ] Data source selected
- [ ] Documentation/schema researched
- [ ] Scope defined (systems, timeframe)
- [ ] Analysis plan created
```

**1. Select Data Source**: Prioritize by security relevance or coverage gaps

**2. Research Data Source**: Understand field meanings and expected values:

```
Action: Run via Splunk MCP
Tool: run_splunk_query
Query: | metadata type=sourcetypes index=<target_index> | table sourcetype, totalCount, lastTime
Purpose: Understand sourcetype coverage
```

**3. Scope**: Define system groups and timeframe (typically 30-90 days)

### Phase 2: Execute

```
Baseline Execution Checklist:
- [ ] Data gathered and filtered
- [ ] Data dictionary created
- [ ] Distributions reviewed
- [ ] Outliers investigated
- [ ] Gaps identified
- [ ] Relationships mapped
```

**1. Create Data Dictionary**: Document key fields:

```
Action: Run via Splunk MCP
Tool: run_splunk_query
Query: index=<target> | head 1000 | fieldsummary | table field, count, distinct_count, is_exact, numeric_count
Purpose: Understand field characteristics
```

**2. Review Distributions**: Establish baselines:

```spl
# Categorical field distribution
index=<target> | stats count by <field> | sort -count | head 20

# Numeric field statistics
index=<target> | stats avg(<field>) median(<field>) stdev(<field>) min(<field>) max(<field>)

# Cardinality check
index=<target> | stats dc(<field>) as unique_values
```

**3. Investigate Outliers**: Apply detection techniques from SPL_PATTERNS.md

**4. Gap Analysis**: Document missing data or quality issues

**5. Identify Relationships**: Map field correlations

### Phase 3: Act

Document baseline including:
- Data dictionary
- Statistical summaries
- Known benign outliers
- Detection candidates

**Create Baseline Dashboard**: Baseline hunts are especially well suited for dashboards. Invoke the `splunk-dashboard-studio` skill to create a baseline monitoring dashboard. Pass it:
- The distribution queries (categorical, numeric, cardinality)
- The data dictionary fields and their characteristics
- Outlier thresholds discovered during the hunt
- The target index, sourcetypes, and scope
- Time range for the baseline period
The resulting dashboard gives analysts a reference view of "normal" to compare against during future investigations.

---

## Model-Assisted Hunt (M-ATH)

Use when hunting requires ML/statistical models to find complex patterns.

### Phase 1: Prepare

```
M-ATH Preparation Checklist:
- [ ] Topic selected with ML approach identified
- [ ] Research completed (methods, datasets)
- [ ] Datasets identified (labeled if supervised)
- [ ] Algorithm(s) selected
```

**Algorithm Selection Guide**:

| Goal | Algorithm Family | Splunk Approach |
|------|------------------|-----------------|
| Classify known threats | Classification | MLTK classifiers |
| Find unusual events | Anomaly detection | MLTK + `| anomalydetection` |
| Group similar events | Clustering | `| cluster` or MLTK |
| Predict future values | Time series | `| predict` |

### Phase 2: Execute

```
M-ATH Execution Checklist:
- [ ] Data gathered and preprocessed
- [ ] Model developed and refined
- [ ] Model applied to hunt data
- [ ] Results analyzed
- [ ] Critical findings escalated
```

**Key SPL for M-ATH**:

```spl
# Anomaly detection
index=<target> | anomalydetection <field> action=annotate

# Time series prediction
index=<target> | timechart count | predict count future_timespan=24

# Clustering
index=<target> | cluster field=<text_field> showcount=true
```

### Phase 3: Act

Same as hypothesis-driven, but also:
- Preserve trained models
- Document model parameters and accuracy
- Consider model-based alerting
- Invoke the `splunk-dashboard-studio` skill to create a model monitoring dashboard that tracks model outputs, anomaly scores, and prediction accuracy over time

---

## Detection Hierarchy

Convert hunt findings to automated detection. Choose the highest feasible level:

| Level | Type | When to Use | Example |
|-------|------|-------------|---------|
| 4 (Best) | **Signatures/Rules** | High confidence, low false positives | ES correlation search |
| 3 | **Analytics in Code** | Complex logic, needs computation | MLTK model, Python script |
| 2 | **Dashboards** | Summarized for analyst review | Daily anomaly dashboard |
| 1 (Lowest) | **Reports** | High false positives, needs expertise | Weekly outlier report |

**For Level 2 (Dashboards)**: Always invoke the `splunk-dashboard-studio` skill. It will take your hunt queries and findings and produce a validated Simple XML dashboard with appropriate visualizations, drilldown, and filtering. This is the recommended output for hunts that identify patterns requiring ongoing human review but are not yet mature enough for fully automated detection (Level 3-4).

---

## MITRE ATT&CK Integration

Map hunts to ATT&CK for coverage tracking. See [MITRE_MAPPING.md](MITRE_MAPPING.md) for technique-specific hunting guidance.

**Query ATT&CK-tagged events** (if ES is deployed):

```spl
index=notable | stats count by mitre_attack_technique_id | sort -count
```

---

## Hunt Metrics

Track these for each hunt:

| Metric | What to Record |
|--------|----------------|
| Detections created/updated | Count and IDs |
| Incidents opened | During hunt + from new detections |
| Gaps identified/closed | Data, visibility, tooling gaps |
| Vulnerabilities found | Misconfigs, missing patches |
| Techniques hunted | ATT&CK IDs covered |

See [HUNT_TEMPLATES.md](HUNT_TEMPLATES.md) for metrics tracking template.

---

## Splunk MCP Server Usage

Always use the Splunk MCP server to run queries:

```
Tool: run_splunk_query
Parameters:
  - query: SPL query string (required)
  - earliest_time: Start time (default: -24h)
  - latest_time: End time (default: now)
  - row_limit: Max results (default: 100, max: 1000)
```

**Other useful tools**:
- `get_indexes`: List available indexes
- `get_knowledge_objects`: List saved searches, alerts, macros, etc.

---

## Additional Resources

- [HUNT_TEMPLATES.md](HUNT_TEMPLATES.md) - Documentation templates
- [SPL_PATTERNS.md](SPL_PATTERNS.md) - Common hunting SPL patterns
- [MITRE_MAPPING.md](MITRE_MAPPING.md) - ATT&CK technique hunting guidance
