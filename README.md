# SemanticEmbed SDK

**Structural intelligence for directed graphs. Six numbers per node. Sub-millisecond.**

SemanticEmbed computes a 6-dimensional structural encoding for every node in a directed graph. From a bare edge list -- no runtime telemetry, no historical data, no tuning -- it produces six independent measurements that fully describe each node's structural role.

> **Validated against production incidents.** In a blind test against a live production environment (100+ services, 2,500+ incidents over 30 days), the majority of topology-relevant incidents occurred on nodes that 6D structural analysis had flagged as risky -- from the call graph alone, before any incident occurred.

---

## Why 6D?

Observability tools tell you **what broke**. SemanticEmbed tells you **what will break** -- from topology alone.

- **No agents, no instrumentation** -- just an edge list
- **Sub-millisecond** -- encodes 100+ node graphs in <1ms
- **Works on any directed graph** -- microservices, AI agent pipelines, data workflows, CI/CD
- **Complementary structural axes** -- six dimensions, each captures risk signals the others cannot

---

## Try It Now

**[Open the Interactive Demo in Google Colab](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/01_quickstart.ipynb)** -- runs in your browser, nothing to install locally.

---

## Install

```bash
pip install semanticembed
```

**Free tier:** Up to 50 nodes per graph. No signup required.

---

## Quick Start

```python
from semanticembed import encode, report

# Any directed graph as an edge list
edges = [
    ("frontend", "api-gateway"),
    ("api-gateway", "order-service"),
    ("api-gateway", "user-service"),
    ("order-service", "payment-service"),
    ("order-service", "inventory-service"),
    ("payment-service", "database"),
]

# Compute the 6D encoding (sub-millisecond)
result = encode(edges)

# Six structural measurements per node
for node, vector in result.vectors.items():
    print(f"{node}: {vector}")

# Structural risk report
print(report(result))
```

Output:

```
STRUCTURAL RISK REPORT
======================

AMPLIFICATION RISKS (high fanout, high criticality):
  - api-gateway    | fanout=0.667 | criticality=0.556

CONVERGENCE SINKS (low independence, many upstream callers):
  - database       | independence=0.000

STRUCTURAL SPOF (low independence, high upstream dependency):
  - api-gateway    | independence=0.000 | every request flows through this node
```

---

## What It Finds That Other Tools Miss

| Your current tools | SemanticEmbed |
|---|---|
| This service has high latency | This service is on 89% of all paths (structural SPOF) |
| This service had 5 errors | This service fans out to 12 downstream services (amplification risk) |
| This service is healthy | This service has zero lateral redundancy (convergence sink) |

Runtime monitoring tells you what is slow **now**. Structural analysis tells you what **will** cause cascading failures regardless of current load.

---

## The Six Dimensions

Every node gets six independent structural measurements:

| Dimension | What It Measures | Risk Signal |
|-----------|-----------------|-------------|
| **Depth** | Position in the execution pipeline (0.0 = entry, 1.0 = deepest) | Deep nodes accumulate upstream latency |
| **Independence** | Lateral redundancy at the same pipeline stage | Low independence = structural chokepoint |
| **Hierarchy** | Module or group membership | Cross-module dependencies = blast radius |
| **Throughput** | Fraction of total traffic flowing through the node | High throughput + low independence = hidden bottleneck |
| **Criticality** | Fraction of end-to-end paths depending on this node | High criticality = SPOF |
| **Fanout** | Broadcaster (1.0) vs aggregator (0.0) | High fanout = amplification risk |

These six properties capture complementary structural information. Each dimension provides risk signals the others cannot.

See [docs/dimensions.md](docs/dimensions.md) for the full reference.

---

## Use Cases

**Microservice architectures** -- Find SPOFs, amplification cascades, and convergence bottlenecks in any service mesh. Works with Kubernetes, Istio, OTel traces, or static architecture diagrams.

**AI agent pipelines** -- Identify vendor concentration risk, gateway bottlenecks, and guardrail single points of failure in LLM orchestration graphs.

**CI/CD and data pipelines** -- Detect structural fragility in build graphs, ETL workflows, and deployment pipelines before they cause cascading failures.

**Architecture drift monitoring** -- Compare structural fingerprints across releases. Know exactly which services changed structural role and by how much.

---

## Notebooks

Step-by-step Colab notebooks. Click to open, run in your browser.

| Notebook | Use Case | What You Learn |
|----------|----------|---------------|
| [01 - Quickstart](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/01_quickstart.ipynb) | Getting started | Install, encode a graph, read the risk report |
| [02 - Dimensions Deep Dive](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/02_dimensions.ipynb) | Understanding 6D | What each dimension means, with worked examples |
| [03 - Drift Detection](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/03_drift_detection.ipynb) | Architecture drift | Compare graph versions, detect structural changes |
| [04 - Bring Your Own Graph](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/04_bring_your_own.ipynb) | Any graph | Load from JSON, OTel traces, or Kubernetes |
| [05 - AI Agent Pipelines](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/05_ai_agent_pipelines.ipynb) | AI/LLM agents | Vendor concentration, gateway bottlenecks, guardrail SPOFs |
| [06 - CI/CD & Data Pipelines](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/06_cicd_pipelines.ipynb) | CI/CD & ETL | Build graph fragility, pipeline bottlenecks, drift gates |
| [07 - OpenTelemetry](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/07_opentelemetry.ipynb) | OTel traces | Extract edges from traces, structural analysis, CI/CD gates |
| [08 - Qwen Compression](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/08_qwen_compression.ipynb) | LLM compression | Structural pruning of Qwen2.5-7B, 10% speedup at Grade A |

---

## Extract Edges from Infrastructure

Don't have an edge list? The `extract` module parses common infrastructure files automatically.

```python
import semanticembed as se

# From Docker Compose
edges = se.extract.from_docker_compose("docker-compose.yml")

# From Kubernetes manifests
edges = se.extract.from_kubernetes("k8s/")

# From GitHub Actions workflows
edges = se.extract.from_github_actions(".github/workflows")

# From Terraform
edges = se.extract.from_terraform("infra/")

# From Python imports (module dependency graph)
edges = se.extract.from_python_imports("src/")

# From Node.js monorepo (inter-package dependencies)
edges = se.extract.from_package_json_workspaces(".")

# From OpenTelemetry traces (OTLP / Jaeger / Zipkin JSON)
edges = se.extract.from_otel_traces("traces.json")

# From AI agent frameworks (AST-only — no need to install the framework)
edges = se.extract.from_langgraph("workflow.py")   # StateGraph.add_edge / add_conditional_edges / set_entry_point
edges = se.extract.from_crewai("crew.py")          # Task(agent=...) / Task(context=...) / Crew(manager_agent=...)
edges = se.extract.from_autogen("agents.py")       # GroupChat(agents=...) / initiate_chat(...)

# Auto-detect everything in a directory
edges, sources = se.extract.from_directory(".")
print(f"Found {len(edges)} edges from {sources}")

# Then encode as usual
result = se.encode(edges)
print(result.table)
```

Requires `pyyaml` for YAML parsing: `pip install 'semanticembed[extract]'`

### Trace ingestion (highest-fidelity edges)

Compose / k8s / Terraform describe deployment, not actual call edges. **Real
runtime traces are the only source with the actual call graph.** v0.3.0 ships
a deterministic parser for the three common JSON formats:

- **OTLP** (OpenTelemetry Collector / SDK exports): `{"resourceSpans": [...]}`
- **Jaeger** (`jaeger-query` API, `jaeger-cli`): `{"data": [{"spans": [...]}]}`
- **Zipkin** (Zipkin v2 API): top-level array with `localEndpoint.serviceName`

Edges are emitted at the **service level** — same-service spans roll up. Place
a `traces.json` (or `otel.json` / `jaeger.json` / `zipkin.json`) at your repo
root and `from_directory()` will pick it up.

### Live observability connectors

Static analysis is great for repos. For *running* infra, pull traces directly:

```python
from semanticembed import live

# Dynatrace — Smartscape services + call relationships
edges = live.from_dynatrace(
    env_url="https://abc12345.live.dynatrace.com",
    api_token=os.environ["DYNATRACE_API_TOKEN"],
)
```

Honeycomb and Datadog connectors are tracked for future releases.

### AI agent frameworks

The three popular Python agent frameworks each have an explicit graph-building
API. Static AST parsing extracts the actual call graph the framework will run.
The SDK does **not** import or run the framework — you don't need
`pip install langgraph` to extract from a LangGraph script.

**LangGraph** — `g.add_edge`, `g.add_conditional_edges` (with explicit
`path_map`), `g.set_entry_point`, `g.set_finish_point`. The sentinels `START`
and `END` are emitted as literal node names.

**CrewAI** — `Task(agent=researcher)` produces `researcher -> task_var`;
`Task(context=[t1, t2])` produces `t1 -> task_var` / `t2 -> task_var`;
`Crew(manager_agent=mgr)` adds a `mgr -> agent` fan-out.

**AutoGen** — `GroupChat(agents=[a, b, c])` with an explicit
`GroupChatManager` produces a star (`manager -> a`, `-> b`, `-> c`).
Without a manager, it's fully connected. `x.initiate_chat(y)` always
produces `x -> y`.

`from_directory()` auto-detects these by scanning Python files for the
relevant `import` statements and only running the matching parser on those
files (cheap and accurate vs. walking the whole tree).

### Blending sources cleanly

Combining traces + compose + Python imports usually produces the same logical
service under several names (`auth-svc`, `auth_svc`, `AuthService`). Use
`dedupe_edges` to canonicalize:

```python
compose_edges, _ = se.extract.from_directory(".")
trace_edges = se.extract.from_otel_traces("traces.json")

edges = se.dedupe_edges(
    list(compose_edges) + trace_edges,
    normalize="snake",                          # AuthService -> auth_service
    aliases={"auth_svc": "auth_service"},       # explicit overrides
)
result = se.encode(edges)
```

Modes: `"none"` (default), `"snake"`, `"lower"`, `"kebab"`. Self-loops are
dropped by default.

---

## LLM-Powered Analysis

Get plain-language explanations and actionable recommendations using your own LLM key.

```python
import semanticembed as se

result = se.encode(edges)

# One-shot analysis (OpenAI, Anthropic, or local Ollama)
print(se.explain(result, model="gpt-4o-mini", api_key="sk-..."))
print(se.explain(result, model="claude-sonnet-4-5", api_key="sk-ant-..."))
print(se.explain(result, model="ollama/llama3"))  # local, no key needed

# Follow-up questions
answer = se.ask(result, "What happens if the database goes down?",
                model="gpt-4o-mini", api_key="sk-...")
```

The LLM sees only the encoding output (6D vectors, risk report) -- never the algorithm.

---

## Structural Diff

Compare two graph versions in one call:

```python
changes = se.encode_diff(edges_v1, edges_v2)
for node, deltas in changes.items():
    for dim, info in deltas.items():
        print(f"{node}.{dim}: {info['before']:.3f} -> {info['after']:.3f}")
```

---

## Agent

An autonomous agent that scans your repo, extracts edges, encodes, and explains results interactively. Choose your LLM backend:

```bash
# Claude agent (installs the agent code + the Anthropic agent SDK)
pip install 'semanticembed[agent-claude]'
export ANTHROPIC_API_KEY=sk-ant-...
semanticembed-agent              # interactive
semanticembed-agent --ask "What is my biggest SPOF?"

# Gemini agent
pip install 'semanticembed[agent-gemini]'
export GOOGLE_API_KEY=...
semanticembed-gemini-agent
```

Both binaries are also reachable as `python -m semanticembed.agent` /
`python -m semanticembed.agent.gemini_agent`.

The agent has 7 tools: scan, extract (docker-compose, k8s, Python imports), encode, diff, and simulate architecture changes. See [src/semanticembed/agent/README.md](src/semanticembed/agent/README.md) for full docs.

### What gets sent where

Be explicit about data egress before pointing the agent at private architecture:

- **Claude agent** (`python -m agent`): the LLM reads tool outputs as conversation context, so the contents of `docker-compose.yml`, Kubernetes manifests, Terraform `.tf` files, Python source, and `package.json` files in your project go to **Anthropic's API** along with your prompts. Conversation history is governed by Anthropic's data-use policies.
- **Gemini agent** (`python -m agent.gemini_agent`): same data flow, sent to **Google's API** instead.
- **Skill** (`skill/analyze.py`): runs **Ollama on your machine**. Raw input never leaves localhost unless you set `SEMBED_OLLAMA_URL` to a remote host.
- **Cloud `encode()` call**: only the **edge list** (node names, e.g. `["frontend", "auth"]`) goes to the SemanticEmbed Railway endpoint. File contents are never sent.

If your topology is sensitive, prefer the skill (local Ollama) or pre-extract edges deterministically with `se.extract.from_directory()` and call `se.encode()` directly — that path sends only the edge list.

---

## Example Graphs

The `examples/` directory contains edge lists for well-known architectures:

| File | Application | Nodes | Edges |
|------|------------|-------|-------|
| [google_online_boutique.json](examples/google_online_boutique.json) | Google Online Boutique (microservices) | 11 | 15 |
| [weaveworks_sock_shop.json](examples/weaveworks_sock_shop.json) | Weaveworks Sock Shop (microservices) | 15 | 15 |
| [ai_agent_pipeline.json](examples/ai_agent_pipeline.json) | Multi-agent LLM orchestration | 12 | 15 |
| [cicd_pipeline.json](examples/cicd_pipeline.json) | CI/CD build pipeline | 13 | 17 |

---

## React Components

Drop-in React components for rendering SDK results. See [examples/react/](examples/react/) for the full source.

| Component | What it renders |
|-----------|----------------|
| `useSemanticEmbed.ts` | React hook — call `encode()` from your frontend |
| `RiskTable.tsx` | Sortable risk table with severity badges |
| `RadarChart.tsx` | 6D radar chart comparing node profiles |
| `TopologySummary.tsx` | KPI cards + risk breakdown |

```tsx
import { useSemanticEmbed } from './useSemanticEmbed';
import { RiskTable } from './RiskTable';

function App() {
  const { result, loading, encode } = useSemanticEmbed();
  return (
    <>
      <button onClick={() => encode([["A","B"],["B","C"],["C","D"]])}>Analyze</button>
      {result && <RiskTable risks={result.risks} />}
    </>
  );
}
```

---

## Input Format

SemanticEmbed accepts any directed graph as an edge list.

```python
# Python tuples
edges = [("A", "B"), ("B", "C")]
result = encode(edges)

# JSON file
result = encode_file("my_graph.json")
```

JSON format:

```json
{
  "edges": [
    {"source": "A", "target": "B"},
    {"source": "B", "target": "C"}
  ]
}
```

See [docs/input_format.md](docs/input_format.md) for the full spec.

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/getting_started.md](docs/getting_started.md) | Install, encode, read results, export -- one page |
| [docs/api_reference.md](docs/api_reference.md) | Every function, class, parameter, and return type |
| [docs/dimensions.md](docs/dimensions.md) | The six structural dimensions -- full reference |
| [docs/input_format.md](docs/input_format.md) | Edge list input specification |
| [docs/output_format.md](docs/output_format.md) | Encoding output and risk report format |

---

## License

SemanticEmbed SDK is proprietary software distributed as a compiled package.
Free tier available for graphs up to 50 nodes. See [LICENSE](LICENSE) for terms.

**Patent pending.** Application #63/994,075.

---

## Contact

Email jeffmurr@seas.upenn.edu
