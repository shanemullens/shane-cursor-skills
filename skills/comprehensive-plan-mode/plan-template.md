# Plan Output Template

Use this structure when calling `CreatePlan` in Phase 3. Map `status: todo` from the directive to `status: pending` in the CreatePlan `todos` array (CreatePlan schema uses `pending`/`in_progress`/`completed`).

```markdown
---
name: [Insert Project/Task Name]
overview: [Insert a 1-2 sentence summary of the goal and approach]
todos:
  - id: [step-1-id]
    content: [Detailed description of step 1]
    status: pending
  - id: [step-2-id]
    content: [Detailed description of step 2]
    status: pending
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
