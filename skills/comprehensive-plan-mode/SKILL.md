---
name: comprehensive-plan-mode
description: Enhances Cursor Plan Mode with a strict three-phase workflow — extreme clarification, targeted research, and detailed plan generation with Mermaid diagrams and validation steps. Attach at the end of Plan Mode prompts when you want maximum plan depth, accuracy, and reviewability before implementation.
disable-model-invocation: true
---

# Comprehensive Plan Mode

## Invocation

Attach this skill at the end of any Plan Mode prompt:

```
[Your task request here]

@comprehensive-plan-mode
```

## Relationship to Default Plan Mode

When this skill is attached, it **supersedes** the default Plan Mode guidance on question brevity ("1-2 critical questions"). Phase 1 requires a comprehensive question list and a hard STOP. All other Plan Mode rules still apply: no edits until approval, use `CreatePlan` for final output.

## Tool Bridge

| Phase | Required agent actions |
|-------|------------------------|
| Phase 1 | Use `AskQuestion` when choices exist; otherwise present a comprehensive bulleted question list. **Do not** call `CreatePlan` or make edits. **STOP** until user responds. |
| Phase 2 | `WebSearch`/`WebFetch` for best practices; search local codebase (`Grep`, `Read`, `Task` explore); synthesize findings before planning. |
| Phase 3 | Call `CreatePlan` with `name`, `overview`, `todos`, and `plan` body matching [plan-template.md](plan-template.md). Wait for explicit approval before any implementation. |

Map `status: todo` from the directive below to `status: pending` in CreatePlan `todos`.

## PLAN MODE DIRECTIVE: MAXIMIZE COMPREHENSIVENESS

You are operating in Cursor's Plan Mode. To ensure the highest quality output, you must strictly follow these three phases. Do not skip any steps.

### PHASE 1: EXTREME CLARIFICATION (DO NOT SKIP)
Do not make any assumptions about my requirements, the environment, or edge cases. Identify *any and all* ambiguity in my request. Be extra chatty and analytical. 
Before writing any plans or code, present a comprehensive, bulleted list of clarifying questions covering:
- Missing technical requirements, constraints, or scope boundaries.
- Expected inputs, outputs, data structures, and edge cases.
- Integration points, dependencies, or specific library versions.
**STOP.** Wait for my answers to these questions before proceeding to Phase 2.

### PHASE 2: TARGETED RESEARCH
Once I have answered your questions, utilize your tools to conduct targeted research. You must:
1. Search the web for best practices, recent updates, or known issues related to the specific subject matter.
2. Check relevant official documentation for the frameworks, APIs, or tools involved.
3. Search the local codebase to gather context on existing patterns, styles, or conflicting implementations.
Synthesize these findings to inform the architecture of your plan.

### PHASE 3: PLAN GENERATION
Generate a highly detailed, reviewable implementation plan. You must wait for my explicit approval of this plan before executing any code. Structure the plan exactly as follows, utilizing YAML frontmatter and Markdown:

```markdown
---
name: [Insert Project/Task Name]
overview: [Insert a 1-2 sentence summary of the goal and approach]
todos:
  - id: [step-1-id]
    content: [Detailed description of step 1]
    status: todo
  - id: [step-2-id]
    content: [Detailed description of step 2]
    status: todo
isProject: false
---

## Scope & Goal
[Detailed explanation of what is being built, the target environment, and the boundaries of the task.]

## Architecture & Flow
[Include a Mermaid.js flowchart or diagram illustrating the architecture, logic flow, or data movement.]

## Core Components & Specifications
[Detailed breakdown of files to create/modify, data structures, and core logic. Use markdown tables where appropriate for mappings, schemas, or API endpoints.]

## Implementation Steps
[Chronological order of execution matching the YAML todos. Detail exactly what will be written in each step.]

## Validation Workflow
[Step-by-step instructions on how we will test and validate the changes post-build (e.g., dry-runs, CLI commands, expected outputs, or log verification).]
```

When calling `CreatePlan`, pass the sections above into the `plan` parameter and mirror the YAML `todos` in the tool's `todos` array (use `status: pending` instead of `status: todo`). See [plan-template.md](plan-template.md) for the CreatePlan-ready version.
