# shane-cursor-skills

Splunk-focused Cursor skills and agents for threat hunting, TA development, dashboard building, AI Toolkit/ML-SPL workflows, log generation, and diag-based root-cause analysis. Works with [Cursor](https://cursor.com) and other AI coding agents that support the [Agent Skills](https://agentskills.io/) specification.

This repository extends [dtherrick/splunk-skills](https://github.com/dtherrick/splunk-skills) with the same `skills/` + `agents/` layout. It adds **splunk-log-generator** and **comprehensive-plan-mode**, and uses the [Vercel skills CLI](https://github.com/vercel-labs/skills) for installation instead of a custom npm package.

## Installation

### Skills (via Vercel skills CLI)

Install all skills globally (available across all projects):

```bash
npx skills add shanemullens/shane-cursor-skills -g -y
```

Install to the current project only:

```bash
npx skills add shanemullens/shane-cursor-skills -y
```

List available skills without installing:

```bash
npx skills add shanemullens/shane-cursor-skills --list
```

Install a specific skill:

```bash
npx skills add shanemullens/shane-cursor-skills --skill peak-threat-hunting -g -y
```

Skills are installed to `~/.cursor/skills/` (global) or `.cursor/skills/` (project).

### Agents (manual install)

The skills CLI installs skills only. To install agents, copy them to your Cursor agents directory.

**macOS / Linux:**

```bash
mkdir -p ~/.cursor/agents
cp agents/*.md ~/.cursor/agents/
```

**Windows (PowerShell):**

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.cursor\agents" | Out-Null
Copy-Item agents\*.md $env:USERPROFILE\.cursor\agents\ -Force
```

Agents are installed to `~/.cursor/agents/`.

## What's Included

### Skills

Skills are instruction sets that guide your AI coding agent through specialized workflows.

| Skill | Description |
|-------|-------------|
| **peak-threat-hunting** | Conduct threat hunts in Splunk using the PEAK framework (Prepare, Execute, Act with Knowledge). Supports hypothesis-driven, baseline, and model-assisted hunts with MITRE ATT&CK mapping. |
| **splunk-ta-development** | Build Splunk Technology Add-ons (TAs) end-to-end — analyze log samples, create props.conf/transforms.conf, load data, and validate field extractions via the Splunk MCP server. |
| **splunk-dashboard-studio** | Build Dashboard Studio dashboards using JSON definitions. Covers visualization types, layout design, tokens, interactivity, Dynamic Options Syntax (DOS), and conditional formatting. |
| **splunk-aitk-mcp** | Operate Splunk AI Toolkit 6.0 through a Splunk MCP server. Covers GenAI (`ai`, `aiagent`), ML-SPL model workflows (`fit`, `apply`, `score`, `summary`, `listmodels`, `deletemodel`, `sample`), environment probing, cost controls, MCP limits, safeguard fallback, and held-out validation. |
| **splunk-log-generator** | Build Python scripts that generate realistic logs for any Splunk sourcetype and send them to Splunk via HEC. Supports catalog mode and scenario mode with correlated IOCs. |
| **splunk-diag-doctor** | Root-cause Splunk deployments from diag bundles. Crawls extracted folders or `.tar.gz` diags, correlates splunkd.log, metrics.log, systeminfo.txt, and conf layers into evidence-backed findings, then writes a remediation plan with ready-to-apply stanzas and CLI. |
| **comprehensive-plan-mode** | Enhances Cursor Plan Mode with a three-phase workflow — clarification, research, and detailed plan generation. Attach at the end of Plan Mode prompts; not auto-invoked (`disable-model-invocation: true`). |

### Agents

Agents are subagent definitions that handle specialized tasks autonomously.

| Agent | Description |
|-------|-------------|
| **dashboard-studio-builder** | Builds Dashboard Studio dashboards as JSON definitions. Full lifecycle: discovers data via Splunk MCP, assembles the definition, deploys, and validates. |

## Publishing (Maintainer)

Local `~/.cursor/skills/` and `~/.cursor/agents/` are the source of truth. To publish changes to this repository:

```powershell
.\scripts\publish-skills.ps1
git push origin main
```

Preview changes without modifying files or git state:

```powershell
.\scripts\publish-skills.ps1 -DryRun
```

Override the commit message:

```powershell
.\scripts\publish-skills.ps1 -CommitMessage "chore: update peak-threat-hunting templates"
```

## Prerequisites

Most Splunk skills and agents require a [Splunk MCP server](https://github.com/livehybrid/splunk-mcp) connection to run queries and deploy dashboards against a Splunk instance.

**splunk-log-generator** requires Python and a Splunk HTTP Event Collector (HEC) endpoint.

**splunk-diag-doctor** works offline from Splunk diag files (extracted folders or `.tar.gz` bundles). No live Splunk connection is required. Python helper scripts in the skill support inventory, log triage, metrics analysis, conf auditing, and system checks.

**splunk-aitk-mcp** requires Splunk AI Toolkit 6.0.0 on Splunk Cloud, the compatible Python for Scientific Computing add-on (PSC 4.3.2 or 4.3.3), a Splunk MCP server, and the capabilities/search-command permissions needed for the requested ML-SPL operation. Its `ai` and `aiagent` workflows can send Splunk data to configured LLM providers and incur per-event costs, so review sensitive fields and bound the first run before scaling.

**comprehensive-plan-mode** is attach-only — add `@comprehensive-plan-mode` to Plan Mode prompts when you want maximum plan depth before implementation.

## License

MIT
