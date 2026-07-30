# splunk-aitk-mcp

A portable skill for driving the **Splunk AI Toolkit 6.0** from Claude Code or Cursor through a
**Splunk MCP Server**, against Splunk Cloud.

Covers the GenAI surface (`ai`, `aiagent`, LLM connections, Agent Launchpad invocation) plus core
ML-SPL (`fit`, `apply`, `score`, `summary`, `listmodels`, `deletemodel`, `sample`).

## What it encodes

- A mandatory environment probe — app version, PSC compatibility, caller capabilities, MCP tool
  surface — before any SPL is written.
- Cost discipline for `ai`, which fires one LLM call per event and is the main way this goes wrong.
- A degradation ladder for risky commands (`ai`, `aiagent`, `fit`, `deletemodel`) that trip SPL
  safeguards and are often refused by read-only MCP transports.
- Strategies for the ~1000-row cap and ~60s execution ceiling, especially silent truncation.
- Validation discipline: no model gets called good without a held-out split and a `score`.

## Layout

```
splunk-aitk-mcp/
├── SKILL.md                          entry point, phased workflow
└── references/
    ├── ml-spl-reference.md           full command syntax, providers, capabilities, perf settings
    ├── prompt-patterns.md            the three ai prompt patterns and their cost profiles
    ├── mcp-execution.md              transport constraints, chunking, artifact mode
    └── troubleshooting.md            symptom → cause → fix
```

## Install — Claude Code

```bash
cp -r splunk-aitk-mcp ~/.claude/skills/
```

Or per-project, at `.claude/skills/splunk-aitk-mcp/`.

## Install — Cursor

Cursor reads project rules from `.cursor/rules/`. Point it at the skill:

```bash
mkdir -p .cursor/rules
cp -r splunk-aitk-mcp .cursor/rules/
```

Then reference `splunk-aitk-mcp/SKILL.md` from your `AGENTS.md` or a project rule so the agent loads
it when Splunk AITK work comes up. The reference files are read on demand from the same directory.

## Assumptions

Written against AITK 6.0.0 on Splunk Cloud, with PSC add-on 4.3.2/4.3.3. Tool names for the Splunk
MCP Server are deliberately not hardcoded — the skill instructs the agent to enumerate its own tool
surface at the start of each task, so it works across MCP server builds and forks.
