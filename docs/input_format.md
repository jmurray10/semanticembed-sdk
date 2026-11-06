# Input Format

SemanticEmbed accepts any directed graph as an edge list.

---

## Python API

**Tuple list:**
```python
from semanticembed import encode
edges = [("A", "B"), ("B", "C"), ("B", "D")]
result = encode(edges)
```

**List of dicts:**
```python
edges = [
    {"source": "A", "target": "B"},
    {"source": "B", "target": "C"},
]
result = encode(edges)
```

**From JSON file:**
```python
from semanticembed import encode_file
result = encode_file("my_graph.json")
```

---

## JSON Format

```json
{
  "name": "optional graph name",
  "description": "optional description",
  "edges": [
    {"source": "A", "target": "B"},
    {"source": "B", "target": "C"}
  ]
}
```

**Required:** `edges` array. Each edge is an object with `source` / `target` (also accepted: `src` / `tgt` or `from` / `to`) or a `[source, target]` pair.

**Optional:** `name`, `description`.

---

## Requirements

- Any directed graph; cycles are accepted. See [docs/scoring_gaps.md](scoring_gaps.md) for how results read on cyclic input.
- At least 2 edges (the client raises `ValueError` otherwise).
- Free tier: 50 nodes max. Paid tier: unlimited.
- Node names: unique strings.
- `encode()` sends edges as given. Use `se.dedupe_edges()` to drop duplicates and self-loops client-side. The `extract.*` parsers already drop self-loops and duplicate edges.

---

## Auto-Extract Edges (deterministic, no LLM)

The `extract` module parses common infrastructure, IaC, and code files directly:

```python
import semanticembed as se

# Container / orchestration
edges = se.extract.from_docker_compose("docker-compose.yml")
edges = se.extract.from_kubernetes("k8s/")
edges = se.extract.from_github_actions(".github/workflows")

# Infrastructure as Code
edges = se.extract.from_terraform("infra/")
edges = se.extract.from_cloudformation("template.yaml")
edges = se.extract.from_aws_cdk("app.py")          # Python CDK
edges = se.extract.from_pulumi("__main__.py")      # Python Pulumi

# Code dependency graphs
edges = se.extract.from_python_imports("src/", depth=2)
edges = se.extract.from_package_json("package.json")
edges = se.extract.from_package_json_workspaces(".")
edges = se.extract.from_pyproject("pyproject.toml")
edges = se.extract.from_requirements("requirements.txt")

# AI agent frameworks (AST-only, no need to install the framework)
edges = se.extract.from_langgraph("workflow.py")
edges = se.extract.from_crewai("crew.py")
edges = se.extract.from_autogen("agents.py")

# OpenTelemetry traces (auto-detects OTLP / Jaeger / Zipkin)
edges = se.extract.from_otel_traces("traces.json")

# Auto-detect everything in a directory
edges, sources = se.extract.from_directory(".")
```

Requires `pyyaml` for the YAML-based parsers: `pip install 'semanticembed[extract]'`.

See [API Reference](api_reference.md#extract-module) for full parameters.

---

## Live Observability Connectors

For *running* infra (not just repo files), use `live.from_*`:

```python
from semanticembed import live

edges = live.from_dynatrace(env_url=..., api_token=...)
edges = live.from_honeycomb(dataset=..., api_key=...)
edges = live.from_datadog(api_key=..., app_key=...)
```

Each makes outbound HTTP requests to the vendor API and retries once on
transient failures. See [API Reference](api_reference.md#live-module) for details.

---

## LLM Fallback for Unknown Formats

If the deterministic parsers don't recognize your code, `find_edges()`
falls through to a Claude or Gemini call that reads your files and
extracts an edge list:

```python
edges, sources, log = se.find_edges(".", provider="claude")
```

`provider` can be `"claude"` (needs `ANTHROPIC_API_KEY` and
`pip install anthropic`) or `"gemini"` (needs `GOOGLE_API_KEY` or
`GEMINI_API_KEY`, and `pip install 'semanticembed[agent-gemini]'`). Both
accept `api_key=` instead of the env var. The deterministic scan is
always tried first; the LLM is only invoked as a fallback, and it sends
file text to the provider. See `find_edges` in the
[API Reference](api_reference.md) for what is sent.

---

## Blending Sources

Combining multiple extractors usually produces the same logical service
under several spellings. Use `dedupe_edges` to canonicalize:

```python
from_compose, _ = se.extract.from_directory(".")
from_traces = se.extract.from_otel_traces("traces.json")

edges = se.dedupe_edges(
    list(from_compose) + from_traces,
    normalize="snake",                          # AuthService -> auth_service
    aliases={"auth_svc": "auth_service"},       # explicit overrides
)
```

---

## Common Data Sources

| Source | How to get edges | Helper |
|--------|-----------------|--------|
| **Docker Compose** | `depends_on`, `links` | `extract.from_docker_compose()` |
| **Kubernetes** | Service selectors, Ingress backends | `extract.from_kubernetes()` |
| **GitHub Actions** | Job `needs` fields | `extract.from_github_actions()` |
| **Terraform** | Resource cross-references | `extract.from_terraform()` |
| **CloudFormation** | `DependsOn` + `Ref`/`Fn::GetAtt`/`Fn::Sub` | `extract.from_cloudformation()` |
| **AWS CDK** (Python) | Construct kwarg references | `extract.from_aws_cdk()` |
| **Pulumi** (Python) | Resource kwarg references | `extract.from_pulumi()` |
| **Python codebase** | Module import graph | `extract.from_python_imports()` |
| **Node.js package** | `dependencies` / `devDependencies` / `peerDependencies` | `extract.from_package_json()` |
| **Node.js monorepo** | Inter-package dependencies | `extract.from_package_json_workspaces()` |
| **pyproject.toml** | PEP 621, dependency groups, Poetry | `extract.from_pyproject()` |
| **requirements.txt** | pip requirements (`-r` followed inside its directory) | `extract.from_requirements()` |
| **OpenTelemetry traces** | Parent-child span service relationships | `extract.from_otel_traces()` |
| **LangGraph workflow** | `add_edge` / `add_conditional_edges` | `extract.from_langgraph()` |
| **CrewAI** | `Task(agent=...)` / `Crew(manager_agent=...)` | `extract.from_crewai()` |
| **AutoGen** | `GroupChat(agents=[...])` / `initiate_chat` | `extract.from_autogen()` |
| **Dynatrace (running)** | Smartscape Entities API v2 | `live.from_dynatrace()` |
| **Honeycomb (running)** | Query API span breakdown | `live.from_honeycomb()` |
| **Datadog (running)** | Spans Search API | `live.from_datadog()` |
| **Other / unknown** | LLM fallback (Claude or Gemini) | `find_edges(provider=...)` |
