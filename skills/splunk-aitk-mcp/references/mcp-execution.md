# Executing AITK Through a Splunk MCP Server

The MCP transport imposes constraints that AITK's documentation never anticipates, because the
docs assume a browser. This file covers working inside them.

## The three constraints

| Constraint | Typical value | What it breaks |
|---|---|---|
| Result cap | ~1000 events | Any `ai` or `apply` over a larger set — silently truncated |
| Execution ceiling | ~60 seconds | `fit` on real data, row-by-row `ai` past a few dozen rows |
| Read-only guardrail | Varies by build | `fit`, `deletemodel`, and sometimes `ai` / `aiagent` entirely |

Confirm the actual values for the server in this session rather than assuming these — they differ
across builds and forks. If the server exposes limits in its tool descriptions or an info tool,
read them.

## Truncation is the dangerous one

A timeout is loud. A truncated result set is silent, and every conclusion drawn from it is wrong in
a way neither you nor the user can see. Defend against it:

**Always establish the true row count before analyzing.** `| stats count` returns one row and is
never truncated, so it tells you the real size regardless of the cap.

```spl
index=web sourcetype=access_combined status>=500 earliest=-24h | stats count
```

**Then check whether your result set is at the boundary.** If a search returns exactly the cap —
1000 rows, or whatever the server's limit is — assume truncation until proven otherwise. Report it
in your caveats every time.

**Reduce on the Splunk side, not in your head.** The pipeline should return a summary, not raw
events you then aggregate yourself. `stats`, `top`, `timechart`, and `dedup` all collapse volume
before it reaches the transport.

## Working within the execution ceiling

`fit` on a meaningful dataset will frequently exceed 60 seconds. Options, in order of preference:

1. **Shrink the training window.** Fit on a representative slice, not all history.
2. **Sample deliberately.** `| sample count=5000 seed=1234` gives a reproducible training set that
   completes in time. Note in your report that the model was fit on a sample.
3. **Accelerate the base search.** If the expensive part is data retrieval rather than the
   algorithm, a data model or summary index fixes it properly. Worth recommending when the user
   will run this repeatedly.
4. **Hand it off.** For a genuine production fit over 30 days of data, the right answer is a
   scheduled saved search in Splunk, not an MCP call. Produce the SPL and say so.

`apply` is much cheaper than `fit` — it's inference against a stored model — so the common pattern
is: fit once in Splunk (scheduled or manual), then `apply` freely over MCP.

## Chunking `ai` across a large set

When row-by-row genuinely is required over more rows than one call can handle, partition
reproducibly rather than using `head` repeatedly (which re-reads the same top rows):

```spl
| inputlookup my_dataset.csv
| sample partitions=10 seed=1234
| search partition_number=1
| ai prompt="..." provider=OpenAI model=gpt-4o-mini
```

Then iterate `partition_number=2`, `3`, and so on. Each chunk is a separate search, each with its
own cost. Tell the user the total call count before starting, not after chunk three.

Before doing this at all, though: check whether Pattern 3 (all-at-once summarization) answers the
actual question. It usually does, for a fraction of the cost.

## When a command is refused

Distinguish the failure modes, because the remedies differ:

- **Capability error** (`apply_ai_commander_command` missing) — the user needs a role change. No SPL
  rewrite helps.
- **Search command permission** — set per-role at Settings → Advanced search → Search commands.
  Also an access problem, not a syntax one.
- **MCP read-only guardrail** — the server refuses the command class. Switch to artifact mode:
  produce copy-pasteable SPL.
- **SPL safeguard** — the risky-command warning. In Splunk Web the user clicks **Run Query Anyway**.
  Over MCP there's no dialog; behaviour depends on the server.

Do not try to defeat any of these. Report which one you hit, in plain terms, and give the user the
finished SPL plus what they need to change to run it themselves. That is a complete, useful answer.

## Artifact mode

When execution is blocked, the deliverable becomes the SPL itself. Make it genuinely ready to run:

- Fully qualified — real index names, real sourcetypes, real field names discovered from the
  environment during Phase 0, not placeholders.
- Bounded — include the `head` or `stats` reduction so the user doesn't fire it unbounded.
- Annotated — a comment or accompanying note on expected cost and row count.
- Warned — tell them the safeguard dialog will appear and that accepting it with **Run Query
  Anyway** is expected for `ai`, `aiagent`, `fit`, and `deletemodel`.

Say clearly that you generated rather than executed it. An agent that implies it ran a search it
didn't run is worse than useless.
