---
name: splunk-aitk-mcp
description: Drive the Splunk AI Toolkit (AITK) 6.0 from Claude Code or Cursor through a Splunk MCP Server — writing and executing ML-SPL such as `ai`, `aiagent`, `fit`, `apply`, `score`, `summary`, `listmodels`, and `deletemodel` against Splunk Cloud. Use this skill whenever the user mentions the AI Toolkit, MLTK, ML-SPL, the `ai` or `aiagent` command, Agent Launchpad, LLM connections in Splunk, training or applying a Splunk ML model, scoring or validating a Splunk model, or asks to summarize/classify/enrich Splunk events with an LLM in the search pipeline — even if they don't name the toolkit explicitly. Also use it when a Splunk search containing `fit`, `apply`, or `ai` fails, times out, truncates at 100k events, or trips an SPL safeguard warning.
---

# Splunk AI Toolkit over MCP

Operate AITK 6.0 on **Splunk Cloud** from an external coding agent whose only reach into Splunk
is a **Splunk MCP Server**. Two things make this different from writing SPL in a browser, and
almost every failure traces back to one of them:

1. **The MCP transport is narrow.** Read-only guardrails, a ~1000-event result cap, and a ~60s
   execution ceiling. AITK's heaviest commands are exactly the ones that strain all three.
2. **`ai` and `aiagent` cost real money per event.** `| ai` fires one LLM call per row. A careless
   pipeline against a busy index is a five-figure invoice and a very slow search. Blast radius is
   the first thing to reason about, not the last.

Work through the phases below in order. Skipping the probe is the single most common way an agent
burns a turn hallucinating a command that the environment was never going to run.

## Phase 0 — Probe before you act

Never assume the tool surface, the app version, or the caller's permissions. Establish all three.

**Map your own MCP tools first.** Tool names vary across Splunk MCP Server builds and forks.
Enumerate the tools actually available in this session and identify which one dispatches a search,
which lists indexes, and which (if any) writes. Use those names for the rest of the task. If no
tool can dispatch a search, stop and tell the user — everything below depends on it.

Then run these probes. All are read-only and none trip a safeguard:

```spl
| rest /services/apps/local | search disabled=0 | table title label version | search title=*ML* OR label="*AI Toolkit*"
```
Confirms AITK is installed and its version. AITK 6.0.0 requires the Python for Scientific Computing
(PSC) add-on 4.3.2 or 4.3.3. A version mismatch here explains a large share of "the command doesn't
exist" reports.

```spl
| rest /services/authentication/current-context | table username roles capabilities
```
Check for the capabilities that gate the work you're about to do:

| Capability | Gates |
|---|---|
| `apply_ai_commander_command` | executing `ai` at all |
| `list_ai_commander_config` | viewing configured LLM providers/models (not tokens) |
| `edit_ai_commander_config` | adding providers, editing tokens and model info |
| `edit_agent_connections` | adding Knowledge Base and MCP connections to agents |
| `list_tokens_scs` | seeing the Splunk-hosted LLM option |

The `mltk_admin` role carries the first three by default. Missing `apply_ai_commander_command` means
every `ai` search will fail on permissions — say so immediately rather than debugging syntax.

```spl
| listmodels
```
Cheap, non-risky, and proves ML-SPL is actually resolvable in this app context. If this errors, the
problem is installation or app context, not your SPL.

Report what you found before proceeding. If AITK is absent or the caller lacks
`apply_ai_commander_command`, the correct move is to say so, not to write speculative SPL.

## Phase 1 — Decide which plane you're operating on

AITK gives you two distinct execution planes, and conflating them produces nonsense.

**The SPL plane** — `ai`, `fit`, `apply`, `score`, `summary`, `listmodels`, `deletemodel`. Stateless
per search, runs inside the search pipeline, results come straight back to you.

**The agent plane** — `aiagent`, which invokes a pre-built Agent Launchpad agent. The agent has its
own LLM, its own system prompt, its own MCP connections (Splunk, Atlassian, Slack, PagerDuty,
GitHub, GitLab, or custom), and its own skills. You are handing off a task, not running a pipeline.

**There is no SPL to create, edit, or delete an Agent Launchpad agent.** Agent creation, agent
skills, and MCP connections are Splunk Web operations only. If the user asks you to build an agent,
be direct that you can draft the system prompt, the skill instructions, and the invocation SPL, but
they will need to create it in the AI Toolkit UI under **Agents → Manage agents**. Don't invent a
`createagent` command or a REST endpoint you haven't verified.

To discover what agents already exist, ask the user or have them check the Agents tab — enumerate
via REST only if you can confirm the endpoint responds, and say plainly when you're guessing.

## Phase 2 — Size the blast radius before writing `ai`

This is the discipline that matters most. Before any pipeline containing `ai`:

1. **Count first.** Run the base search with `| stats count` and know the row count.
2. **Choose a prompt pattern deliberately** (see `references/prompt-patterns.md`). Row-by-row is
   N LLM calls; all-at-once is one. The choice is a cost decision as much as an analytical one.
3. **Always bound the first run.** Put `| head 3` before `| ai` on the first execution, every time,
   even when the user is confident. Show them the output and the extrapolated cost before scaling.
4. **Never let `ai` sit downstream of an unbounded search.** If you cannot prove the row count is
   small, aggregate with `stats` or `dedup` first.

A pipeline that would fire more than ~50 LLM calls should be surfaced to the user with the count and
an explicit confirmation before you run it — not run and apologized for afterward.

The toolkit does not inspect what you send to the LLM. Splunk data leaves the platform for an
external provider. If the base search touches anything that looks sensitive — PII, credentials,
customer identifiers, raw payloads — flag it before executing, not after. Redact or aggregate
upstream of `ai` where you can.

## Phase 3 — Handle the safeguard, and degrade gracefully when blocked

`fit`, `deletemodel`, `ai`, and `aiagent` are classified by Splunk as risky commands. In Splunk Web
they raise a warning dialog with a "Run Query Anyway" option. Over MCP there is no dialog to click,
and many Splunk MCP Server builds refuse non-generating or write-capable commands outright.

So treat executability as **unknown until tested**, and use this ladder:

1. **Probe once, cheaply.** Try the smallest possible risky command — `| makeresults | ai prompt="Reply with the single word OK"`
   with a bounded model — and see what comes back.
2. **If it executes**, proceed normally and note in your report that the risky-command path is open.
3. **If it's rejected** (permission error, read-only guardrail, safeguard block), stop trying to
   force it. Switch to **artifact mode**: produce the finished, copy-pasteable SPL, explain exactly
   where to paste it, and warn that Splunk will show a safeguard dialog they should accept with
   **Run Query Anyway**. This is a legitimate successful outcome, not a failure — say so plainly
   rather than burning turns on workarounds.
4. **Never** attempt to disable SPL safeguards, alter `limits.conf`, or route around the MCP
   server's read-only guardrail to get a command through. If the guardrail is in the way, the answer
   is to tell the user, not to defeat it.

## Phase 4 — Write the SPL

Full syntax for every command is in `references/ml-spl-reference.md`. Read it before writing
anything non-trivial; the parameter surfaces differ more than they look.

The essentials:

**`ai`** takes `prompt`, `provider`, `model` (and `kb_id` for Bedrock Knowledge Base RAG). Omit
`provider` and `model` when a default LLM connection is configured. Interpolate fields into the
prompt with braces:

```spl
| inputlookup http_error_dataset.csv
| head 3
| ai prompt="HTTP Error '{HTTP_Code}' occurred with message: '{Error_Message}'. Root cause: '{Root_Cause}'. What specific steps resolve this? Be precise." provider=OpenAI model=gpt-4
```

Chained calls read the previous result as `{ai_result_1}`, `{ai_result_2}`, and so on.

**`aiagent`** takes only `prompt` and `agent_name`. `prompt` is optional when the agent was created
with a default task prompt. It is a generating command:

```spl
| aiagent prompt="An alert fired: {alert_description}. Pull related Jira and Confluence context, then summarize." agent_name=CoolAgentName
```

**`fit` / `apply` / `score`** follow the classic MLTK shape. `fit <algorithm> [options] <response> from <explanatory> [into <model>]`,
then `apply <model> [as <field>]`, then `score <method> <actual> against <predicted>`. Models are
Splunk lookup objects and obey lookup permissions and namespacing.

## Phase 5 — Validate before you claim anything

An `apply` that returns a column is not evidence the model works. Before describing any model as
good, accurate, or production-ready:

- Hold out data. `| sample partitions=100 seed=1234` then filter on `partition_number` gives a
  reproducible split.
- Score it. `confusion_matrix` and `roc_auc_score` for classifiers, `r2_score` / `rmse` for
  regressors. Nest multiple scores under `multireport`.
- Report the actual numbers. If you couldn't validate — because the MCP cap truncated results, or
  `fit` was blocked — say that explicitly instead of implying the model was checked.

For `ai` and `aiagent` output there is **no guardrail on what the LLM returns**. Treat responses as
unverified assertions. Never present LLM-generated root-cause analysis, regex, or remediation steps
as fact without labeling them as model output that needs human review.

## Reporting

Structure findings like this:

```
## What I ran
[the SPL, verbatim, with row counts]

## Results
[findings, with the numbers]

## Caveats
[truncation, blocked commands, unvalidated LLM output, cost incurred]

## Next steps
[what needs a human, and where]
```

Always report cost-relevant facts: how many LLM calls fired, against which provider and model.
Always report when results hit the MCP row cap — a truncated result set silently misrepresents the
data, and a conclusion drawn from it is wrong in a way the user can't see.

## Reference files

- `references/ml-spl-reference.md` — full syntax and parameters for every ML-SPL command, plus
  provider list, roles/capabilities, and performance settings. Read before writing SPL.
- `references/prompt-patterns.md` — the three `ai` prompt patterns with cost profiles, and guidance
  on writing prompts that survive contact with messy Splunk fields.
- `references/mcp-execution.md` — working within the row cap, execution ceiling, and read-only
  guardrail; chunking and aggregation strategies. Read when a search truncates or times out.
- `references/troubleshooting.md` — symptom-to-cause table for the failures you'll actually hit.
  Read when something errors rather than guessing at syntax.
