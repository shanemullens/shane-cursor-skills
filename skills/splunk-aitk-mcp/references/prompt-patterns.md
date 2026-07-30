# `ai` Prompt Patterns

Three documented patterns. The choice is primarily a **cost and latency decision**, and only
secondarily an analytical one — pick deliberately and tell the user which you picked and why.

## Pattern 1 — Row-by-row

One LLM call per event. Suitable for micro-analysis where each record genuinely needs its own
answer.

```spl
| inputlookup http_error_dataset.csv
| head 10
| ai prompt="HTTP Error '{HTTP_Code}' occurred with message: '{Error_Message}'. Root cause: '{Root_Cause}'. What specific steps can we take to resolve this? Provide a precise but informative answer." provider=OpenAI model=gpt-4
```

**Cost: N calls.** This is the pattern that produces surprise invoices. It is also the one people
reach for by default because it reads most naturally. Bound it with `head` or a `stats`-based
reduction unless the user has explicitly accepted the row count.

## Pattern 2 — Multi-chain

Chains prompts, where a later prompt consumes an earlier result via `{ai_result_1}`. Suitable for
step-by-step investigation: analyze, then act on the analysis.

```spl
| inputlookup http_error_dataset.csv
| search HTTP_Code="500"
| head 5
| ai prompt="The server responded with '{HTTP_Code}' and message: '{Error_Message}'. Root cause: '{Root_Cause}'. What could be the broader operational impact?" provider=Anthropic model=claude-3-sonnet
| ai prompt="Given the operational impact: '{ai_result_1}', suggest proactive monitoring and recovery measures." provider=Gemini model=gemini-1.5-pro
```

**Cost: N × number of chained stages.** Two `ai` commands over 100 rows is 200 calls. Chain depth
multiplies, it does not add.

Different providers can be used per stage — a cheap fast model for extraction, a stronger one for
reasoning, is a reasonable cost optimization.

## Pattern 3 — All data at once (summarization)

Aggregate first, then send one collective prompt. Suitable for trends, recurring patterns, and
holistic analysis.

```spl
| inputlookup http_error_dataset.csv
| stats values(*) as *
| ai prompt="Analyze the common root causes among the HTTP errors provided. The list includes error codes '{HTTP_Code}', messages '{Error_Message}', and root causes '{Root_Cause}'. Provide a consolidated summary of recurring issues and mitigation strategies." provider=AzureOpenAI model=gpt-3.5-turbo
```

**Cost: 1 call.** This is the right default over MCP. It sidesteps the row cap, finishes inside the
execution ceiling, and costs a fraction of row-by-row. When a user asks to "summarize these logs,"
this is almost always what they actually want.

The tradeoff is the model's context window. `stats values(*)` over a large result set will overflow
it. Reduce first — `stats count by` the dimension that matters, `dedup`, or `top` — so you send
shape rather than volume.

---

## Writing prompts that survive real Splunk data

**Brace interpolation is literal.** `{Error_Message}` pulls that field verbatim. If the field is
missing on some events, or holds a multi-value, or contains braces or quotes of its own, the prompt
degrades in ways that are hard to see in the output. Normalize upstream: `fillnull`, `mvjoin`,
`coalesce`, `substr` for long raw payloads.

**Constrain the output shape.** Free-form LLM prose is painful to use downstream in SPL. Ask for
something parseable when the result feeds another command:

```
prompt="Classify this error as exactly one of: TRANSIENT, CONFIG, CAPACITY, SECURITY. Reply with the single word only. Error: '{Error_Message}'"
```

Then `| eval category=ai_result_1` behaves predictably.

**Keep raw events out of the prompt where a field will do.** `{_raw}` is expensive, noisy, and the
most likely route for sensitive data to leave the platform. Extract the fields you need first.

**Ask for uncertainty explicitly.** Splunk operators act on these outputs. A prompt ending
"If the provided information is insufficient to determine the cause, say so rather than guessing"
measurably reduces confident fabrication in remediation advice.

---

## Bedrock Knowledge Base RAG

With a Bedrock connection, add `kb_id` to ground responses in your own runbooks, incident history,
and internal procedures rather than generic model knowledge. This is the difference between
"check your database connection pool" and instructions that name your actual systems and
escalation path. Worth proposing whenever a user is frustrated that `ai` output is too generic.

---

## What the output is, and is not

There are no guardrails on what the LLM returns. Nothing validates it against the source data.
Treat every `ai_result` as an unverified assertion — particularly regex, root-cause claims, and
remediation steps, all three of which are plausible-sounding and confidently wrong at a meaningful
rate. Label them as model output in any report, and never let generated regex reach production
field extractions without someone testing it.
