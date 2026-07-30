# Troubleshooting AITK over MCP

Match the symptom, then apply the fix. Resist rewriting SPL syntax before checking whether the
cause is environmental — most of these failures are not syntax problems.

## Command not found / unknown search command

| Check | Detail |
|---|---|
| Is AITK installed? | `\| rest /services/apps/local \| search disabled=0 \| table title label version` |
| Is PSC the right version? | AITK 6.0.0 requires PSC add-on 4.3.2 or 4.3.3 (Python 3.13). Mismatched PSC is the most common cause. |
| Clean PSC install? | Upgrading PSC requires removing previous versions first. A layered install leaves the toolkit broken in confusing ways. |
| Right app context? | ML-SPL resolves per app. Run `\| listmodels` as the cheapest possible proof the commands exist. |
| Right command era? | `ai` requires 5.6.0+. `aiagent` and Agent Launchpad require 6.0.0+. |

## Permission errors on `ai`

Two independent gates, and both must pass:

1. The `apply_ai_commander_command` capability, normally via `mltk_admin`.
2. Per-role search command permissions at **Settings → Advanced search → Search commands →
   Permissions**.

Verify with `| rest /services/authentication/current-context | table username roles capabilities`.

## Bedrock model dropdown is empty

The IAM setup is incomplete. Required: an IAM role carrying `AmazonBedrockFullAccess`; an IAM user
with programmatic access and an inline `sts:AssumeRole` policy targeting that role's ARN; and the
user added to the role's trust relationship. Without all three, no models enumerate.

## Splunk hosted LLM option not visible

Requires the `list_tokens_scs` capability, and AITK 5.7.0 or higher.

## Search returns nothing after `fit`

`fit` drops every event that has one or more null fields, and drops fields that are null across all
events. A single sparse field can silently empty the training set. Diagnose by counting before and
after:

```spl
<base search> | stats count
<base search> | fields <your field list> | where isnotnull(field1) AND isnotnull(field2) | stats count
```

Fix upstream with `fillnull`, `coalesce`, or by dropping the sparse field from the model.

## Results cut off at exactly 100,000

Reservoir sampling. Default `max_inputs` is 100,000 events before `fit`. Raise it in the AI Toolkit
app Settings UI — but confirm the search head has the memory to match, and raise
`max_memory_usage_mb` alongside it.

## Results cut off at ~1000

That's the MCP transport cap, not Splunk. See `mcp-execution.md`. Aggregate with `stats` rather than
raising anything.

## Search times out

- If it's `fit`: raise `max_fit_time`, or shrink the training set with `sample`.
- If it's the MCP call: you're against the ~60s transport ceiling. Reduce the work or move it to a
  scheduled search in Splunk.
- If it's row-by-row `ai`: each row is a network round trip to an LLM. Switch to all-at-once
  summarization or chunk by partition.

## Memory errors

Raise `max_memory_usage_mb` for the algorithm in the AI Toolkit app Settings UI. Confirm available
resources first — this is a real allocation, not a soft limit.

## Categorical field missing from the model

Non-numeric fields with more than 100 distinct values are discarded (`max_distinct_cat_values`).
High-cardinality fields like `src_ip`, `user`, or `url` hit this constantly. Either raise the limit,
or — usually better — reduce cardinality upstream: bucket the field, take the top N and bin the
rest as `other`, or engineer a feature from it instead of feeding it raw.

## Security warning dialog on `fit` / `ai` / `aiagent` / `deletemodel`

Expected. These are classified as risky commands. In Splunk Web the dialog appears on first run
after login, after a page refresh, when using **Open in Search** from the toolkit, and on some
Showcase examples. Accept with **Run Query Anyway**.

Do not attempt to deactivate SPL safeguards to work around this. If a user asks you to, explain
that the safeguard is doing its job and that accepting the dialog is the intended path.

## `apply` fails with `savedsearch`

Not fully supported. Rewrite with `appendcols`:

```spl
| savedsearch MySavedSearch
| appendcols [| inputlookup source.csv | apply "my_model" | table predicted_field]
```

## Multiple `score` commands fail

They must be nested under `multireport`, one score per subsearch bracket. See
`ml-spl-reference.md` section 8.

## Sample search returns nothing

Documentation examples use their own indexes, sourcetypes, and field names. Retarget them to the
actual environment — discover real values in Phase 0 rather than pasting examples verbatim. Debug
by building the pipeline one command at a time over a short window.

## `ai` output is generic and unhelpful

Three usual causes, in order of likelihood:

1. The prompt lacks environment context. The model doesn't know your systems.
2. Field interpolation is producing empty or malformed values — check that `{field}` names match
   the actual result fields, and that they aren't multi-value or null.
3. No grounding. With Bedrock, `kb_id` against a knowledge base of your runbooks turns generic
   advice into specific instructions.

## Model behaves differently after re-fitting

There is no model version history in AITK. Models are lookup objects — version them the way you'd
version any knowledge object, by naming convention and copying files. Consider whether the training
window shifted, or whether reservoir sampling engaged on one run and not the other.
