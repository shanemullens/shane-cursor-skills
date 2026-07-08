# Hunt Documentation Templates

Templates for documenting PEAK threat hunts.

---

## Hunt Report Template

Use this template for documenting each hunt.

```markdown
# Hunt Report: [Hunt Title]

## Metadata
- **Hunt ID**: HUNT-YYYY-###
- **Hunt Type**: Hypothesis / Baseline / M-ATH
- **Hunter(s)**: [Names]
- **Date Range**: YYYY-MM-DD to YYYY-MM-DD
- **Status**: In Progress / Complete

## Executive Summary
[1-2 paragraph summary of the hunt and key findings]

---

## Prepare Phase

### Topic/Data Source
[What are you hunting for or baselining?]

### Hypothesis (if applicable)
[Testable statement following ABLE framework]

| ABLE Component | Description |
|----------------|-------------|
| Actor | |
| Behavior | |
| Location | |
| Evidence | |

### Research Summary
- Key threat intelligence:
- Existing detections reviewed:
- Prior related hunts:
- MITRE ATT&CK techniques: [T####, T####]

### Data Sources
| Index | Sourcetype | Time Range | Event Count |
|-------|------------|------------|-------------|
| | | | |

---

## Execute Phase

### Data Collection
[Describe data gathered and any preprocessing]

### Analysis Methodology
[Describe techniques used: LFO, clustering, visualization, ML, etc.]

### Key Queries

#### Query 1: [Purpose]
```spl
[SPL query]
```
**Result Summary**: [What did this reveal?]

#### Query 2: [Purpose]
```spl
[SPL query]
```
**Result Summary**: [What did this reveal?]

### Findings

#### Finding 1: [Title]
- **Severity**: Critical / High / Medium / Low / Informational
- **Description**: 
- **Evidence**: 
- **Recommendation**: 

#### Finding 2: [Title]
[Repeat structure]

### Hypothesis Result
- [ ] Confirmed - evidence found
- [ ] Refuted - no evidence of this activity
- [ ] Inconclusive - insufficient data/visibility

---

## Act Phase

### Incidents Escalated
| Incident ID | Description | Status |
|-------------|-------------|--------|
| | | |

### Detections Created/Updated
| Detection ID | Type | Description | Hierarchy Level |
|--------------|------|-------------|-----------------|
| | | | |

### Gaps Identified
| Gap Type | Description | Owner | Status |
|----------|-------------|-------|--------|
| Data | | | |
| Visibility | | | |
| Tooling | | | |

### New Hunt Ideas
| Idea | Priority | Notes |
|------|----------|-------|
| | | |

### Stakeholder Communication
- [ ] SOC notified
- [ ] IR team briefed (if incidents)
- [ ] Detection engineering engaged
- [ ] System owners notified

---

## Metrics Summary

| Metric | Count |
|--------|-------|
| Detections created | |
| Detections updated | |
| Incidents opened (during hunt) | |
| Incidents opened (from new detections) | |
| Gaps identified | |
| Gaps closed | |
| Vulnerabilities/misconfigs found | |
| ATT&CK techniques hunted | |

---

## Appendix

### A. Full Query Log
[All queries run during the hunt]

### B. Data Samples
[Representative data samples if helpful]

### C. References
[Links to threat intel, prior hunts, documentation]
```

---

## Baseline Documentation Template

Additional sections for baseline hunts.

```markdown
## Data Dictionary

### Field Inventory
| Field Name | Data Type | Description | Cardinality | Security Relevance |
|------------|-----------|-------------|-------------|-------------------|
| | Numeric/Categorical/Text/DateTime/Boolean | | High/Medium/Low | High/Medium/Low |

### Field Value Distributions

#### [Field Name]
- **Type**: [Categorical/Numeric]
- **Distinct values**: [count]
- **Top values**: 
  | Value | Count | % |
  |-------|-------|---|
  | | | |
- **Notes**: [Any observations]

### Statistical Baselines (Numeric Fields)
| Field | Mean | Median | Std Dev | Min | Max | Notes |
|-------|------|--------|---------|-----|-----|-------|
| | | | | | | |

### Known Benign Outliers
| Field | Value/Pattern | Reason for Exclusion | Date Added |
|-------|---------------|----------------------|------------|
| | | | |

### Field Relationships
| Field A | Field B | Relationship | Notes |
|---------|---------|--------------|-------|
| | | Correlated / Anti-correlated / Dependent | |
```

---

## Metrics Tracking Template

Track cumulative hunt program metrics.

```markdown
# Hunt Program Metrics - [Quarter/Year]

## Summary
| Metric | This Period | YTD | Trend |
|--------|-------------|-----|-------|
| Hunts completed | | | |
| Detections created | | | |
| Detections updated | | | |
| Incidents opened | | | |
| Gaps identified | | | |
| Gaps closed | | | |
| Vulnerabilities found | | | |
| Vulnerabilities remediated | | | |

## Hunt Coverage by Type
| Hunt Type | Count | % of Total |
|-----------|-------|------------|
| Hypothesis-driven | | |
| Baseline | | |
| Model-Assisted | | |

## ATT&CK Coverage
| Tactic | Techniques Hunted | % Coverage |
|--------|-------------------|------------|
| Initial Access | | |
| Execution | | |
| Persistence | | |
| Privilege Escalation | | |
| Defense Evasion | | |
| Credential Access | | |
| Discovery | | |
| Lateral Movement | | |
| Collection | | |
| Command and Control | | |
| Exfiltration | | |
| Impact | | |

## Detection Hierarchy Distribution
| Level | Count | % |
|-------|-------|---|
| 4 - Signatures/Rules | | |
| 3 - Analytics in Code | | |
| 2 - Dashboards | | |
| 1 - Reports | | |

## Hunt Backlog
| Priority | Hunt Idea | Source | Est. Effort |
|----------|-----------|--------|-------------|
| High | | | |
| Medium | | | |
| Low | | | |
```

---

## Quick Hunt Log

For rapid documentation during hunts.

```markdown
# Hunt Log: [Hunt Title]
Date: YYYY-MM-DD

## Progress Notes

### [HH:MM] - [Activity]
[Notes, observations, decisions]

Query run:
```spl
[query]
```
Result: [brief summary]

### [HH:MM] - [Activity]
[Continue logging...]

## Quick Findings
- [ ] Finding: [description]
- [ ] Finding: [description]

## Follow-up Actions
- [ ] Action needed
- [ ] Action needed
```
