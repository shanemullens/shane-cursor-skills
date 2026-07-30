# ML-SPL Command Reference (AITK 6.0)

Contents:
1. Command index
2. `ai`
3. `aiagent`
4. `fit`
5. `apply`
6. `summary`, `listmodels`, `deletemodel`
7. `sample`
8. `score`
9. LLM providers and connections
10. Roles and capabilities
11. Performance settings
12. Search macros

---

## 1. Command index

| Command | Purpose | Risky? |
|---|---|---|
| `ai` | Send pipeline data to an external LLM, response returns to the pipeline | Yes |
| `aiagent` | Invoke an Agent Launchpad agent | Yes |
| `fit` | Train a model and apply it to current results | Yes |
| `apply` | Apply a previously fit model to new results | No |
| `summary` | Return an algorithm-specific summary of a fit model | No |
| `listmodels` | List models created by `fit` | No |
| `deletemodel` | Delete a fit model | Yes |
| `sample` | Randomly sample or partition events | No |
| `score` | Statistical tests to validate model outcomes | No |

"Risky" means the command triggers Splunk's SPL safeguard warning in Splunk Web and may be refused
outright by a read-only MCP transport. See the degradation ladder in SKILL.md Phase 3.

`fit` and `apply` work on relative time ranges but **will not complete on real-time searches**.

---

## 2. `ai`

Introduced in AITK 5.6.0. Sends data to an externally hosted LLM and returns the response into the
search pipeline. Splunk is not providing the LLM — data leaves the platform.

### Parameters

| Parameter | Description |
|---|---|
| `prompt` | The text sent to the LLM. Interpolate result fields with `{field_name}`. |
| `provider` | LLM service provider, e.g. `OpenAI`, `Anthropic`, `Ollama`. Optional if a default connection is configured. |
| `model` | Model identifier, e.g. `gpt-4o-mini`, `llama3-8b-8192`. Optional if a default is configured. |
| `kb_id` | AWS Bedrock Knowledge Base ID, for Retrieval-Augmented Generation against your own runbooks and documentation. Bedrock connections only. |

### Output fields

The first `ai` in a pipeline writes `ai_result_1`, the second writes `ai_result_2`, and so on.
Reference an earlier result inside a later prompt as `{ai_result_1}`.

### Behaviour worth knowing

- One LLM call per event. Cost and latency scale linearly with row count.
- The command does not inspect the input before sending it. There is no PII filter.
- There are no guardrails on the response. Output is unvalidated model text.

### Example

```spl
| inputlookup http_error_dataset.csv
| head 10
| ai prompt="HTTP Error '{HTTP_Code}' occurred with message: '{Error_Message}'. Root cause: '{Root_Cause}'. What specific steps can we take to resolve this? Provide a precise but informative answer." provider=OpenAI model=gpt-4
```

---

## 3. `aiagent`

Generally available in AITK 6.0.0. Invokes an agent built in Agent Launchpad.

### Parameters

| Parameter | Description |
|---|---|
| `prompt` | Task for the agent, in natural language. Optional if a default task prompt was set when the agent was created. |
| `agent_name` | Name of the agent. Set at creation time; alphanumeric, no spaces or special characters. |

### Examples

```spl
| makeresults | aiagent prompt="Hey how are you?" agent_name="TestAgent007"
```

```spl
| aiagent prompt="An alert has been received: {alert_description}. Fetch all relevant resources from Confluence, Jira, and related knowledge sources for this alert. Then format a summary of those resources and provide it" agent_name=CoolAgentName
```

### What lives on the agent, not in the SPL

Agents are configured in Splunk Web (**Agents → Manage agents → +Agent**) with an LLM connection,
temperature (default 0.7), max tokens (default 5000), reasoning effort (None / Low / Medium / High),
a system prompt, a default prompt, MCP connections, and Agent Skills. None of this is settable from
SPL. Agents are Private by default.

A single agent can hold **multiple MCP connections of the same type** — for example two Splunk MCP
connections pointing at different stacks — and reason across both in one invocation. Supported MCP
providers: Splunk, Atlassian, Slack, PagerDuty, GitHub, GitLab, and custom. Custom connections
support Basic Auth, API key, Bearer Token, and OAuth 2.0.

Agents can also be attached to Splunk alerts as the **Run AI Agent** trigger action; alert name,
time, results, and search are passed automatically.

Agent run history is visible under **Agentic AI → Agent run history**, filterable by time range,
agent name, and owner. You only see runs you own or that are shared with your role.

---

## 4. `fit`

```
fit <algorithm> [option_name]=[option_value]... [into <model_name>]
fit <algorithm> [options]... <response-field> [into <model_name>]
fit <algorithm> [options]... <explanatory-field> [into <model_name>]
fit <algorithm> [options]... <response-field> from <explanatory-field> [into <model_name>]
```

`from` is required only when both a response field and explanatory fields are present. `into` saves
the model for later `apply`. Not all algorithms support saved models.

```spl
... | fit LinearRegression errors from _time into errors_over_time
... | fit LogisticRegression species from petal_length petal_width sepal_length sepal_width
```

### What `fit` silently does to your data

The original indexed data is never modified, but the in-memory copy is transformed before training:

- Fields that are null across all events are dropped, and **every event with one or more null fields
  is dropped**. This can quietly shrink your training set to nothing. If that matters, fix it
  upstream in the search.
- Non-numeric fields with more than 100 distinct values are discarded
  (`max_distinct_cat_values`, default 100).
- Remaining non-numeric fields are one-hot encoded into dummy variables.
- Reservoir sampling kicks in above 100,000 events by default (`max_inputs`).

Algorithms supporting incremental `partial_fit`: BernoulliNB, Birch, GaussianNB, MLPClassifier,
StandardScaler, SGDClassifier, SGDRegressor, StateSpaceForecast.

---

## 5. `apply`

```
apply <model_name> [as <output_field>]
```

```spl
... | apply errors_over_time
... | apply errors_over_time as predicted_errors
```

Can run against different search results than those used to fit, but the field list must match.
`apply` repeats `fit`'s field selection and preparation steps: null-field drops, one-hot encoding,
discarding dummy values absent from the learned model, and filling missing dummies with 0.

**`apply` is not fully supported with `savedsearch`.** Rewrite using `appendcols`:

```spl
| savedsearch MySavedSearch
| appendcols [| inputlookup track_day.csv | apply "example_vehicle_type" | table vehicleType]
```

---

## 6. `summary`, `listmodels`, `deletemodel`

```
summary <model_name>
listmodels
deletemodel <model_name>
```

`summary` output is algorithm-specific — coefficients for LinearRegression, per-class coefficients
for LogisticRegression. `listmodels` shows the algorithm and arguments used at fit time, which is
the fastest way to understand a model someone else built.

Models are Splunk lookup objects. They follow lookup namespacing and permission rules, can be
renamed like any knowledge object, and can be moved between instances by copying the files. There is
no built-in model version history.

---

## 7. `sample`

```
sample [ratio=<float 0-1>] [count=<positive integer>] [proportional=<numeric field> [inverse]]
       [partitions=<integer >1> [fieldname=<string>]] [seed=<number>] [by <split_by_field>]
```

| Mode / option | Meaning |
|---|---|
| `ratio` | Probability each event is included. `0.01` ≈ 1%. Use when an approximation is fine. |
| `count` | Exact number of randomly chosen events. Returns all if count exceeds available. |
| `proportional` | Numeric field name determining per-event sampling probability (biased sampling). |
| `partitions` | Randomly divide events into N approximately equal partitions. |
| `seed` | Fixes the random seed for reproducible results. Always set this for train/test splits. |
| `fieldname` | Field holding the partition number. Defaults to `partition_number`. |
| `by <field>` | Return `count` events per value of the field. |
| `inverse` | With `proportional`, inverts the probability. |

This is not the same as the Event Sampling menu in Splunk Web — that samples before data leaves the
indexes, `sample` operates inside the pipeline and supports partitioning and biased sampling.

```spl
... | sample partitions=100 seed=1234 | search partition_number > 70
```

---

## 8. `score`

```
... | score <method> a_field_1 ... a_field_n against b_field_1 ... b_field_m
... | score <method> array_a against array_b [options]
... | score <method> <label_field> against <feature_field_1> ... metric=<option>
```

```spl
... | score confusion_matrix true="species" pred="predicted(species)"
```

Method classes: Classification, Clustering scoring, Pairwise distances scoring, Regression scoring,
Statistical functions (`statsfunctions`), Statistical testing (`statstest`). K-fold scoring is
available for overfitting checks. Scoring methods are not customizable.

**Multiple scores require nesting under `multireport`:**

```spl
| inputlookup track_day.csv
| sample partitions=100 seed=1234
| search partition_number > 70
| apply example_vehicle_type as DT_prediction probabilities=true
| multireport
  [| score confusion_matrix vehicleType against DT_prediction]
  [| score roc_auc_score vehicleType against "probability(vehicleType=2013 Audi RS5)" pos_label="2013 Audi RS5"]
```

---

## 9. LLM providers and connections

Configured in the AI Toolkit under **Connections → Connections → +Connection → LLM**.

Supported providers: Splunk hosted LLM, Custom LLM connection, OpenAI, Anthropic, AzureOpenAI,
Groq, Gemini, Bedrock, Ollama.

**Splunk hosted LLM** (5.7.0+) offers OpenAI GPT-OSS 120B, OpenAI GPT-OSS 20B, and
Llama-3.1-FoundationAI-SecurityLLM-base-1.1-8B. Requires the `list_tokens_scs` capability. This is
the lowest-friction option for a Cloud stack: no external egress, no third-party API key.

**Bedrock** needs extra setup before any models appear in the model dropdown: an IAM role with
`AmazonBedrockFullAccess`, plus an IAM user with an inline `sts:AssumeRole` policy pointed at that
role's ARN, with the user added to the role's trust relationship. If the model dropdown is empty,
this is almost always why.

The Container connection type (Docker / Kubernetes) exists for Splunk App for Data Science and Deep
Learning workloads and is not used by `ai` or `aiagent`.

---

## 10. Roles and capabilities

Role `mltk_admin` carries the first three by default.

| Capability | Grants |
|---|---|
| `apply_ai_commander_command` | Execute the `ai` command |
| `list_ai_commander_config` | View configured providers and models (not API tokens) |
| `edit_ai_commander_config` | Add providers, modify tokens and model info |
| `edit_agent_connections` | Add Knowledge Base and MCP connections to agents |
| `list_tokens_scs` | See and select the Splunk hosted LLM option |

Container work additionally needs `dsdl_admin` capabilities: `list_container_connections`,
`setup_container_configuration`, `enable_hpa`, `list_containers`, `control_containers`,
`fit_mltkcontainer`, `apply_mltkcontainer`.

Access to `fit`, `apply`, and `ai` can also be restricted per-role at
**Settings → Advanced search → Search commands → Permissions**. A user can hold
`apply_ai_commander_command` and still be blocked there — check both when diagnosing a permission
error.

---

## 11. Performance settings

Defaults are deliberately conservative. On Splunk Cloud, change these in the **AI Toolkit app
Settings UI**, not by editing `mlspl.conf` directly.

| Setting | Controls | Symptom when too low |
|---|---|---|
| `max_inputs` | Events before reservoir sampling engages (default 100,000) | Results cut off at 100k |
| `max_fit_time` | Seconds allowed for `fit` | Search times out with an error |
| `max_memory_usage_mb` | Memory ceiling per algorithm | Memory-related search errors |
| `max_distinct_cat_values` | Distinct values allowed in a categorical field (default 100) | High-cardinality fields silently dropped |

Raising these requires the compute and memory to back them. `max_inputs` in the millions is normal
on a dedicated ML search head and reckless on a shared one.

---

## 12. Search macros

Three ship with the toolkit, useful for model validation without hand-writing the stats:

- Classification statistics macro (and classification report macro)
- Confusion matrix macro (and confusion matrix report macro)
- Regression statistics macro
