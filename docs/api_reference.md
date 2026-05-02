# API Reference

Complete reference for the `semanticembed` Python SDK.

---

## Functions

### `encode(edges, *, license_key=None, api_url=None, timeout=60.0, cache=False)`

Encode a directed graph and return 6D structural coordinates.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `edges` | `list` | required | Edge list. Accepts tuples `("A", "B")`, lists `["A", "B"]`, or dicts `{"source": "A", "target": "B"}` |
| `license_key` | `str` | `None` | API key for paid tier. If not provided, checks module attribute, env var, then config file. |
| `api_url` | `str` | `None` | Override API endpoint (for testing). Default: SemanticEmbed cloud API. |
| `timeout` | `float` | `60.0` | Request timeout in seconds. |
| `cache` | `bool` | `False` | If `True`, store the result in an in-process LRU keyed on the order-independent edge set. Repeat calls return immediately without an HTTP round trip. Cache is shared with `aencode`. |

**Behavior:**

- **Pre-flight node-count guard:** if no license key is set and the graph has more than 50 nodes, raises `NodeLimitError` *before* the HTTP call.
- **Retry-once on transient failures:** 502, 503, 504, `ConnectError`, `ReadTimeout` retry once with 0.5 s backoff. 4xx errors propagate immediately.

**Returns:** `SemanticResult`

**Raises:**

| Exception | When |
|-----------|------|
| `NodeLimitError` | Graph exceeds plan node limit (50 free, higher for paid) |
| `AuthenticationError` | Invalid or revoked API key |
| `SemanticConnectionError` | Cannot reach the API |
| `APIError` | Server returned an error |
| `ValueError` | Fewer than 2 edges or malformed edge data |

**Example:**

```python
from semanticembed import encode

result = encode([
    ("frontend", "backend"),
    ("backend", "database"),
    ("backend", "cache"),
])
```

---

### `encode_file(path, *, license_key=None, api_url=None, timeout=30.0)`

Encode a graph from a JSON file.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str` | required | Path to JSON file with `"edges"` array |
| `license_key` | `str` | `None` | API key |
| `api_url` | `str` | `None` | Override API endpoint |
| `timeout` | `float` | `30.0` | Request timeout |

**Returns:** `SemanticResult`

**JSON file format:**

```json
{
  "edges": [
    {"source": "A", "target": "B"},
    {"source": "B", "target": "C"}
  ]
}
```

---

### `report(result)`

Generate a structural risk report from an encoding result.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `result` | `SemanticResult` | Return value from `encode()` or `encode_file()` |

**Returns:** `RiskReport`

**Example:**

```python
from semanticembed import encode, report

result = encode(edges)
risk = report(result)
print(risk)                           # formatted text report
risk.by_category("amplification")     # filter by risk type
risk.by_severity("warning")           # filter by severity
risk.json()                           # JSON-serializable list
```

---

### `drift(before, after)`

Compare two encoding results and return per-node, per-dimension deltas.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `before` | `SemanticResult` | Encoding of the earlier graph version |
| `after` | `SemanticResult` | Encoding of the later graph version |

**Returns:** `dict[str, dict[str, float]]`

Dictionary mapping node names to dimension deltas. Only nodes with changes are included. Positive values mean the dimension increased.

**Example:**

```python
from semanticembed import encode, drift

v1 = encode(edges_before)
v2 = encode(edges_after)
changes = drift(v1, v2)

for node, deltas in changes.items():
    print(f"{node}: {deltas}")
# payment: {'throughput': 0.058, 'fanout': -0.167}
```

---

### `explain(result, *, model, api_key=None)`

Generate a plain-language explanation of the encoding output using your
own LLM key. The function sends only the encoding output (vectors + risk
report) to the LLM — never the algorithm, never your raw graph topology.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `result` | `SemanticResult` | required | Output of `encode()` / `aencode()`. |
| `model` | `str` | required | Model identifier. Common forms: `"gpt-4o-mini"`, `"gpt-4o"`, `"claude-sonnet-4-5"`, `"claude-haiku"`, or `"ollama/<model>"` for a local Ollama instance. |
| `api_key` | `str` | `None` | Provider API key. Required for OpenAI / Anthropic; optional for Ollama (uses local server). |

**Returns:** `str` — natural-language summary, suitable for printing or piping to a chat UI.

```python
print(se.explain(result, model="gpt-4o-mini", api_key=os.environ["OPENAI_API_KEY"]))
print(se.explain(result, model="ollama/llama3"))  # local, no key needed
```

---

### `ask(result, question, *, model, api_key=None)`

Follow-up Q&A on an encoding output. Same data-flow guarantee as
`explain`: only the structural output is sent to the LLM.

```python
answer = se.ask(
    result,
    "What's the biggest single point of failure?",
    model="gpt-4o-mini",
    api_key=os.environ["OPENAI_API_KEY"],
)
```

---

### `aencode(edges, *, license_key=None, api_url=None, timeout=60.0, cache=False)`

Async version of `encode`. Same preflight node-count guard, same retry-once
on transient failures, same optional cache (shared with the sync side).

```python
import asyncio, semanticembed as se

async def main():
    result = await se.aencode([("a", "b"), ("b", "c")], cache=True)
    print(result.table)

asyncio.run(main())
```

---

### `aencode_file(path, *, license_key=None, api_url=None, timeout=60.0, cache=False)`

Async version of `encode_file`.

---

### `aencode_diff(before, after, *, detail=True, license_key=None, api_url=None, timeout=60.0, cache=False)`

Async version of `encode_diff`. Issues both encodes in parallel via
`asyncio.gather`, halving wall time on cold starts.

---

### `clear_encode_cache()`

Empty the in-process encode result cache (used by both `encode(cache=True)`
and `aencode(cache=True)`). The cache holds at most 64 entries with LRU
eviction.

---

### `find_edges(path=".", *, provider="claude", model=None, api_key=None, max_nodes=None)`

Programmatic agent hook — runs `extract.from_directory(path)` first
(deterministic, no LLM, no network egress beyond the encode call). If no
edges are found, falls through to a Claude or Gemini call that reads the
files and produces an edge list.

**Returns** `(edges, sources, log)` — the same `(edges, sources)` shape as
`from_directory`, plus a list of strings describing the steps taken.

---

### `dedupe_edges(edges, *, normalize="none", aliases=None, drop_self_loops=True)`

Canonicalize node names and remove duplicate edges. Use when blending
extractor outputs (compose + traces + Python imports often produce the
same logical service under several names).

| `normalize` | Effect |
|---|---|
| `"none"` | Names unchanged; only exact duplicates merged. |
| `"snake"` | `AuthService` / `auth-svc` → `auth_service` / `auth_svc`. |
| `"lower"` | Lowercase only. |
| `"kebab"` | Like `"snake"` but with dashes. |

`aliases` is an explicit `{variant: canonical}` map applied AFTER
normalization for cases where the rule isn't enough.

```python
edges = se.dedupe_edges(
    list(compose_edges) + trace_edges,
    normalize="snake",
    aliases={"auth_svc": "auth_service"},
)
```

---

## Classes

### `SemanticResult`

Returned by `encode()` and `encode_file()`.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `vectors` | `dict[str, list[float]]` | Node name → 6D vector `[depth, independence, hierarchy, throughput, criticality, fanout]` |
| `graph_info` | `dict` | `{"nodes": int, "edges": int, "max_depth": int}` |
| `encoding_time_ms` | `float` | Round-trip encoding time in milliseconds |
| `risks` | `list[RiskEntry]` | Detected structural risks |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `result[node]` | `list[float]` | 6D vector for a node (subscript access) |
| `result.dimensions(node)` | `dict[str, float]` | Named dimensions: `{"depth": 0.0, "independence": 0.5, ...}` |
| `result.nodes` | `list[str]` | All node names |
| `result.table` | `str` | Formatted table sorted by criticality |
| `result.json()` | `dict` | Full result as JSON-serializable dict |

---

### `RiskReport`

Returned by `report()`.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `risks` | `list[RiskEntry]` | All detected risks |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `str(report)` | `str` | Formatted text report grouped by category |
| `report.by_category(name)` | `list[RiskEntry]` | Filter by category (case-insensitive, e.g. `"amplification"`) |
| `report.by_severity(level)` | `list[RiskEntry]` | Filter by severity (`"critical"`, `"warning"`, `"info"`) |
| `report.json()` | `list[dict]` | All risks as JSON-serializable list |

---

### `RiskEntry`

A single structural risk finding.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `node` | `str` | Affected node name |
| `category` | `str` | Risk type: `SINGLE_POINT_OF_FAILURE`, `AMPLIFICATION_RISK`, `CONVERGENCE_SINK`, `DEEP_BOTTLENECK`, `MONITORING_GAP_CANDIDATE` |
| `severity` | `str` | `"critical"`, `"warning"`, or `"info"` |
| `description` | `str` | Human-readable explanation |
| `value` | `float` | The metric value that triggered the risk |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `entry.json()` | `dict` | JSON-serializable dict |

---

## Exceptions

All exceptions inherit from `SemanticEmbedError`.

| Exception | When | Key attributes |
|-----------|------|---------------|
| `SemanticEmbedError` | Base class for all SDK errors | — |
| `NodeLimitError` | Graph exceeds node limit | `.n_nodes`, `.limit` |
| `AuthenticationError` | Invalid or missing API key | — |
| `APIError` | Server returned an error | `.status`, `.detail` |
| `SemanticConnectionError` | Cannot connect to API | — |

**Example:**

```python
from semanticembed import encode, NodeLimitError, AuthenticationError

try:
    result = encode(edges)
except NodeLimitError as e:
    print(f"Too many nodes: {e.n_nodes} > {e.limit}")
except AuthenticationError:
    print("Check your API key")
```

---

## Configuration

### License key resolution order

The SDK checks for an API key in this order:

1. **Explicit argument:** `encode(edges, license_key="se-...")`
2. **Module attribute:** `semanticembed.license_key = "se-..."`
3. **Environment variable:** `SEMANTICEMBED_LICENSE_KEY` or `SEMANTICEMBED_API_KEY`
4. **Config file:** `~/.semanticembed/license`
5. **Free tier:** No key, 50-node limit

### API URL override

For testing or self-hosted deployments:

```python
result = encode(edges, api_url="http://localhost:8000")
```

Or via environment variable:

```bash
export SEMANTICEMBED_API_URL=http://localhost:8000
```

---

## Constants

### `DIMENSION_NAMES`

```python
from semanticembed import DIMENSION_NAMES
# ["depth", "independence", "hierarchy", "throughput", "criticality", "fanout"]
```

The canonical ordering of the six dimensions. Vectors in `result.vectors` follow this order.

---

## `extract` Module

Extract edges from infrastructure and code files. Import as `se.extract` or `from semanticembed import extract`.

Requires `pyyaml` for YAML parsing: `pip install pyyaml`

### `extract.from_docker_compose(path="docker-compose.yml")`

Parse `depends_on` and `links` from a Docker Compose file.

**Returns:** `list[tuple[str, str]]`

```python
edges = se.extract.from_docker_compose("docker-compose.yml")
```

### `extract.from_kubernetes(path=".")`

Parse Service/Deployment/Ingress selectors and env var references from Kubernetes YAML.

**Parameters:** `path` — a YAML file or directory of YAML files.

**Returns:** `list[tuple[str, str]]`

```python
edges = se.extract.from_kubernetes("k8s/")
```

### `extract.from_github_actions(path=".github/workflows")`

Parse job `needs` fields from GitHub Actions workflow files.

**Returns:** `list[tuple[str, str]]`

```python
edges = se.extract.from_github_actions()
```

### `extract.from_terraform(path=".")`

Parse resource cross-references from `.tf` files.

**Returns:** `list[tuple[str, str]]`

```python
edges = se.extract.from_terraform("infra/")
```

### `extract.from_package_json(path="package.json")`

Parse `dependencies`, `devDependencies`, and `peerDependencies` from a single package.json.

**Returns:** `list[tuple[str, str]]`

```python
edges = se.extract.from_package_json("package.json")
```

### `extract.from_package_json_workspaces(path=".")`

Find inter-package dependency edges in a monorepo. Only includes edges between local workspace packages.

**Returns:** `list[tuple[str, str]]`

```python
edges = se.extract.from_package_json_workspaces(".")
```

### `extract.from_cloudformation(path)`

Parse a CloudFormation template (YAML or JSON). Honors explicit
`DependsOn` lists plus implicit references via `Ref` / `Fn::GetAtt` /
`Fn::Sub`. Pass a directory to merge edges across multiple templates.

```python
edges = se.extract.from_cloudformation("template.yaml")
edges = se.extract.from_cloudformation("infra/")
```

---

### `extract.from_aws_cdk(path)`

Parse an AWS CDK Python file. Detects `aws_xxx.Class(self, "Id", ...)`
constructor calls and emits an edge for every kwarg whose value is a
previously-assigned construct variable. TypeScript CDK is not yet
supported — convert to CFN with `cdk synth` and use `from_cloudformation`.

---

### `extract.from_pulumi(path)`

Parse a Pulumi Python program. Same kwarg-reference logic as CDK, with
the Pulumi resource shape `aws.x.Y("name", ...)` (string as first arg).

---

### `extract.from_otel_traces(path)`

Parse OpenTelemetry trace JSON. Auto-detects OTLP, Jaeger, or Zipkin
format. Emits edges at the **service level** — same-service spans roll
up automatically.

```python
edges = se.extract.from_otel_traces("traces.json")
```

---

### `extract.from_langgraph(path)`

Parse a LangGraph workflow file via AST. Recognizes `add_edge`,
`add_conditional_edges` (with explicit `path_map`), `set_entry_point`
(emits `START -> X`), and `set_finish_point` (emits `X -> END`).

---

### `extract.from_crewai(path)`

Parse a CrewAI script. Patterns: `Task(agent=X)` produces `X -> task_var`;
`Task(context=[t1, t2])` produces `t1 -> task_var` / `t2 -> task_var`;
`Crew(manager_agent=mgr)` adds `mgr -> agent` fan-out.

---

### `extract.from_autogen(path)`

Parse a Microsoft AutoGen / AG2 script. `GroupChat(agents=[...])` with an
explicit `GroupChatManager` produces a star (`manager -> a`); without a
manager, fully connected. Plus `x.initiate_chat(y)` → `x -> y`.

---

### `extract.from_python_imports(path=".", *, depth=None)`

Extract module dependency edges from import statements.

| `depth` | Behavior |
|---|---|
| `None` (default) | Use the last component of each module path (e.g. `myapp.auth.user` → `user`). |
| `1` | Top-level package only. |
| `N` | First N path components — useful for `services/<svc>/...` monorepos at `depth=2`. |

---

### `extract.from_directory(path=".")`

Auto-detect and parse all recognized formats in a directory.

**Returns:** `tuple[list[tuple[str, str]], dict[str, int]]` — edges and a dict mapping source format to edge count.

```python
edges, sources = se.extract.from_directory(".")
print(f"Found {len(edges)} edges from {sources}")
# Found 23 edges from {'docker-compose': 8, 'python-imports': 15}
```

---

## Edge Input Formats

All three formats are accepted and can be mixed:

```python
# Tuples
edges = [("A", "B"), ("B", "C")]

# Lists
edges = [["A", "B"], ["B", "C"]]

# Dicts (source/target keys)
edges = [
    {"source": "A", "target": "B"},
    {"source": "B", "target": "C"},
]
```

Dict keys accepted: `source`/`src`/`from` and `target`/`tgt`/`to`.

---

## `live` Module — Live Observability Connectors

Unlike `extract.*` which parses local files, `live.*` makes outbound HTTP
requests to third-party APIs. Same return shape: `list[tuple[str, str]]`.
Each connector retries once on 502/503/504/`ConnectError`/`ReadTimeout`
with a 0.5 s backoff.

### `live.from_dynatrace(env_url=None, *, api_token=None, timeout=30.0)`

Pull service-to-service edges from Smartscape via the Dynatrace
Environment API v2. Falls back to `DYNATRACE_ENV_URL` /
`DYNATRACE_API_TOKEN` env vars.

```python
from semanticembed import live
edges = live.from_dynatrace(
    env_url="https://abc12345.live.dynatrace.com",
    api_token=os.environ["DYNATRACE_API_TOKEN"],
)
```

---

### `live.from_honeycomb(dataset=None, *, api_key=None, api_url="https://api.honeycomb.io", lookback_seconds=3600, max_spans=10_000, timeout=60.0)`

Issue a Honeycomb Query API request that breaks down spans by
`trace.span_id` / `trace.parent_id` / `service.name`, then derives
parent-child service edges. Override `api_url` for EU tenants
(`https://api.eu1.honeycomb.io`). Falls back to `HONEYCOMB_DATASET` /
`HONEYCOMB_API_KEY`.

---

### `live.from_datadog(*, api_key=None, app_key=None, site="datadoghq.com", lookback="now-1h", max_spans=1000, env=None, service=None, timeout=30.0)`

Call the Datadog Spans Search API and derive edges from `parent_id`
references. Optional `env` and `service` filters; `site` override for
EU/US3/US5 tenants. Falls back to `DD_API_KEY` / `DD_APP_KEY` (also
accepts `DATADOG_API_KEY` / `DATADOG_APP_KEY`).
