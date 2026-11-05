# SemanticEmbed SDK

[![PyPI](https://img.shields.io/pypi/v/semanticembed.svg)](https://pypi.org/project/semanticembed/)
[![Python](https://img.shields.io/pypi/pyversions/semanticembed.svg)](https://pypi.org/project/semanticembed/)
[![CI](https://github.com/jmurray10/semanticembed-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/jmurray10/semanticembed-sdk/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-source--available-blue.svg)](LICENSE-FAQ.md)
[![Free tier](https://img.shields.io/badge/free%20tier-50%20nodes%2C%20no%20signup-brightgreen.svg)](#install)
[![Patent Pending](https://img.shields.io/badge/patent-%2363%2F994%2C075-orange.svg)](LICENSE-FAQ.md#patent)
[![Changelog](https://img.shields.io/badge/changelog-current-success.svg)](CHANGELOG.md)

**Structural risk for directed graphs — especially AI agent pipelines.** Six numbers per node. Sub-millisecond server-side compute.

SemanticEmbed computes a 6-dimensional structural encoding for every node in a directed graph. From a bare edge list — no runtime telemetry, no historical data, no tuning — it produces six complementary measurements that capture distinct aspects of each node's structural role (depth, lateral redundancy, community, throughput, path criticality, broadcast vs aggregation).

**Designed for the topologies traditional observability misses:**

- **AI agent pipelines** — vendor concentration, gateway bottlenecks, guardrail SPOFs in LangGraph / CrewAI / AutoGen workflows
- **Microservices** — SPOFs, amplification cascades, convergence sinks across compose / k8s / Istio
- **CI/CD and data pipelines** — build graph fragility, ETL bottlenecks, drift gates

> **Live demos:**
> - **[Hugging Face Space](https://huggingface.co/spaces/jmurray10/semanticembed-agent-risk)** — zero-install. Paste a LangGraph / CrewAI / AutoGen file, get the encoding + risk findings.
> - **[Demo dashboard](https://semanticembed-dashboard.vercel.app/)** — interactive 6D explorer with 4 reference apps (sign-in required; click "Try Demo" on the login page for a no-account walkthrough).

> **One private-environment blind test.** On one Dynatrace tenant (108 services, 569 topology-relevant incidents over 30 days), **79.6%** of those incidents (453/569) were on nodes the hosted scorer had flagged. That run is not reproducible from this repo: the matcher and the risk thresholds live in a private service. See [validation methodology](docs/validation_methodology.md). It is one tenant, not a general accuracy number.

---

## Why 6D?

Observability tools tell you **what broke**. SemanticEmbed tells you **what will break** — from topology alone.

- **No agents, no instrumentation** — just an edge list
- **Sub-millisecond server-side compute is not something this SDK can show.** `result.encoding_time_ms` is the HTTP round trip, not a kernel timer. The encode response has no separate compute-time field. From this environment on 2026-11-04 a 7-node graph returned in about 0.3–0.4 s, which is faster than the old "typically 0.5–2 s" line. A 100-node kernel time is not measurable on the free tier (the client refuses graphs over 50 nodes before the request).
- **Works on any directed graph** — AI agent pipelines, microservices, data workflows, CI/CD
- **Complementary structural axes** — six dimensions, each captures risk signals the others cannot
- **16 deterministic edge parsers + 3 live connectors** — docker-compose, Kubernetes, GitHub Actions, Terraform, CloudFormation, CDK, Pulumi, Python imports, package.json, npm workspaces, pyproject.toml, requirements.txt, OTel JSON, LangGraph, CrewAI, AutoGen; plus Dynatrace, Honeycomb, and Datadog clients

---

## Install

```bash
pip install semanticembed              # core
pip install 'semanticembed[extract]'   # adds pyyaml for k8s/CFN/CDK parsing
pip install 'semanticembed[agent-claude]'  # adds Claude agent CLI
```

**Free tier:** up to 50 nodes per graph, no signup. See [CHANGELOG](CHANGELOG.md) for what's new.

---

## Quick Start

`from_directory` discovers edges. `encode` sends the edge list to the hosted API. Risk text is produced on the server; this package only prints it.

The block below is the report the API returned on **2026-11-04** for this edge list. If the server scorer changes, the words change. It is not a fixture baked into the client.

```python
import semanticembed as se

edges = [
    ("frontend", "api-gateway"),
    ("api-gateway", "order-service"),
    ("api-gateway", "user-service"),
    ("order-service", "payment-service"),
    ("order-service", "inventory-service"),
    ("payment-service", "database"),
]
result = se.encode(edges)
print(se.report(result))
```

Output (hosted API, 2026-11-04):

```
STRUCTURAL RISK REPORT
======================

SINGLE POINT OF FAILURE:
  - order-service                  | order-service has high structural criticality (0.122) with limited lateral redundancy (independence=0.00). Failure here impacts 6 transitive path pairs.
  - api-gateway                    | api-gateway has high structural criticality (0.102) with limited lateral redundancy (independence=0.50). Failure here impacts 5 transitive path pairs.

MONITORING GAP CANDIDATE:
  - order-service                  | order-service has high criticality (0.122) but sits at depth 0.50, not at the service mesh edge. Likely missing from edge-level observability.
  - api-gateway                    | api-gateway has high criticality (0.102) but sits at depth 0.25, not at the service mesh edge. Likely missing from edge-level observability.
  - payment-service                | payment-service has high criticality (0.061) but sits at depth 0.75, not at the service mesh edge. Likely missing from edge-level observability.

DEEP BOTTLENECK:
  - order-service                  | order-service is a bottleneck deep in the pipeline (depth=0.50, criticality=0.122). Failures here are harder to diagnose from edge monitoring.
  - payment-service                | payment-service is a bottleneck deep in the pipeline (depth=0.75, criticality=0.061). Failures here are harder to diagnose from edge monitoring.

WHAT TO DO
----------
  >> api-gateway, order-service: Add a redundant path or fallback service so this node is not the only option at its pipeline stage.
  >> api-gateway, order-service, payment-service: Ensure this node has dedicated monitoring. It sits on critical paths but is not at the service edge, so it may be missing from your dashboards.
  >> order-service, payment-service: Add health checks and timeouts. Deep bottlenecks are hard to diagnose from edge monitoring — ensure this node has dedicated alerting.

Total: 7 risks (5 critical, 2 warning, 0 info)
```

Directory scan is the same `encode` call after `edges, sources = se.extract.from_directory(".")`. The 16 parsers are docker-compose, Kubernetes, GitHub Actions, Terraform, CloudFormation, AWS CDK (Python), Pulumi (Python), Python imports, `package.json`, npm workspaces, `pyproject.toml`, `requirements.txt`, OpenTelemetry JSON, LangGraph, CrewAI, and AutoGen. The three live connectors are Dynatrace, Honeycomb, and Datadog; this check did not call those APIs.

**Held-out extraction, 2026-11-04.** Hand-labeled files. Micro precision **1.0**, recall **1.0** (55/55 edges, 6 files). Tuning was also 1.0 (59/59 edges, 13 files). Pinned SHAs are in [corpus/manifest.json](corpus/manifest.json). Re-run with `python scripts/corpus_score.py --split held-out`. The only pin that was behind HEAD was this repo (`a612cec` vs `4f1cec9`); the labeled files in it produced the same edges. `package.json` workspaces are covered by a unit test, not by a pinned monorepo.

Two held-out files sit in repos that also contain a tuning file (`crewAI-examples` recruitment crew, `pulumi/examples` S3 website). Those files were not used to edit the parsers.

Hosted scoring behavior for the voting-app shape, identical twins, and cyclic LangGraph graphs is described in [docs/scoring_gaps.md](docs/scoring_gaps.md). The client forwards the edge list; those three outcomes are server rules, not client bugs.

**Or try it without installing** — [open the Quickstart in Google Colab](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/01_quickstart.ipynb).

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

Every node gets six complementary structural measurements:

| Dimension | What It Measures | Risk Signal |
|-----------|-----------------|-------------|
| **Depth** | Position in the execution pipeline (0.0 = entry, 1.0 = deepest) | Deep nodes accumulate upstream latency |
| **Independence** | Lateral redundancy at the same pipeline stage | Low independence = structural chokepoint |
| **Hierarchy** | Module or group membership | Cross-module dependencies = blast radius |
| **Throughput** | Fraction of total traffic flowing through the node | High throughput + low independence = hidden bottleneck |
| **Criticality** | Fraction of end-to-end paths depending on this node | High criticality = SPOF |
| **Fanout** | Broadcaster (1.0) vs aggregator (0.0) | High fanout = amplification risk |

These six properties capture complementary structural information. The
risk patterns documented below combine specific axes; no single axis is a
complete risk signal on its own.

See [docs/dimensions.md](docs/dimensions.md) for axis definitions, the
formal invariance properties of the encoding, and the empirical
correlation results vs standard graph centrality.

---

## Use Cases

**Microservice architectures** -- Find SPOFs, amplification cascades, and convergence bottlenecks in any service mesh. Works with Kubernetes, Istio, OTel traces, or static architecture diagrams.

**AI agent pipelines** -- Identify vendor concentration risk, gateway bottlenecks, and guardrail single points of failure in LLM orchestration graphs.

**CI/CD and data pipelines** -- Detect structural fragility in build graphs, ETL workflows, and deployment pipelines before they cause cascading failures.

**Architecture drift monitoring** -- Compare structural fingerprints across releases. Know exactly which services changed structural role and by how much.

---

## What's new in v0.7

- **Modern AutoGen patterns + lenient edge parser + better error messages** (v0.7.3)
- **`live.from_dynatrace` / `from_honeycomb` / `from_datadog`** — pull real call edges from running infra (v0.5–v0.7)
- **OpenTelemetry trace ingestion** — auto-detects OTLP / Jaeger / Zipkin (v0.3)
- **AI agent framework parsers** — `from_langgraph`, `from_crewai`, `from_autogen`, AST-only, no need to install the framework (v0.4)
- **IaC parsers** — CloudFormation, AWS CDK (Python), Pulumi (Python) (v0.6)
- **Async surface** — `await aencode(...)`, `aencode_diff()` runs both encodes in parallel (v0.7.1)
- **`encode(cache=True)`** — skip the HTTP round trip on repeat calls (v0.4.1)
- **`dedupe_edges`** — canonicalize names when blending multiple sources (v0.3)
- **One-retry-on-5xx** — every connector handles transient failures (v0.7.2)
- **`semanticembed-agent` console script** — interactive shell for non-programmer users (v0.5.1)

Full details in the [CHANGELOG](CHANGELOG.md).

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
| [09 - Quantum Reachability (IBM Q free tier)](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/09_quantum_reachability.ipynb) | Quantum cross-validation | Continuous-time quantum walk on a directed graph, run on IBM Q Open Plan, cross-checked vs SDK criticality |

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
# Resource names that collide (`aws_vpc.this` and `aws_internet_gateway.this`)
# are labeled `type.name`. On terraform-aws-modules/terraform-aws-vpc
# `b3abd6df` that is 119 edges and 96 nodes, over the free-tier cap.
# The root `*.tf` files alone are 73 nodes. A license is required to encode them.

# From CloudFormation (YAML or JSON)
edges = se.extract.from_cloudformation("template.yaml")

# From AWS CDK (Python)
edges = se.extract.from_aws_cdk("app.py")

# From Pulumi (Python)
edges = se.extract.from_pulumi("__main__.py")

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

# Honeycomb — Query API over a dataset
edges = live.from_honeycomb(
    dataset="my-app-prod",
    api_key=os.environ["HONEYCOMB_API_KEY"],
    lookback_seconds=900,
)

# Datadog — Spans Search API
edges = live.from_datadog(
    api_key=os.environ["DD_API_KEY"],
    app_key=os.environ["DD_APP_KEY"],
    env="prod",
    lookback="now-30m",
)
```

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

- **Claude agent** (`semanticembed-agent` / `python -m semanticembed.agent`): the LLM sees your prompts and what the SemanticEmbed tools return: edge lists (node names), which parsers found them, encoding results, and error messages. That goes to **Anthropic's API** and is governed by Anthropic's data-use policies. The agent has no built-in tools (no shell, file read, or web fetch), and it does not load `.claude/settings.json`, hooks, or `CLAUDE.md` from the project it scans. Requires `claude-agent-sdk>=0.1.60`.
- **Gemini agent** (`semanticembed-gemini-agent` / `python -m semanticembed.agent.gemini_agent`): same data flow, sent to **Google's API** instead.
- **`find_edges()` LLM fallback**: only when the deterministic scan finds no edges, it sends the text of compose, Kubernetes, Terraform, GitHub Actions, `package.json`, `pyproject.toml`, `Pipfile` and `requirements.txt` files (up to 250 KB) to **Anthropic** (`provider="claude"`) or **Google** (`provider="gemini"`). It skips `node_modules`, `.venv`, `vendor` and similar directories, skips files that resolve outside the scanned path, and replaces secret-looking values (keys, tokens, passwords, URL credentials, Kubernetes `Secret` data) with `[REDACTED]`. Redaction is pattern-based and can miss a secret.
- **`explain()` / `ask()`**: send the encoding result (node names, the six values per node, risk flags, graph size) and your question to the model you name: **OpenAI**, **Anthropic**, or a local **Ollama** server. No file contents.
- **Claude Code skill** (`skill/analyze.py`): runs **inside Claude Code** — uses the parent agent for any natural-language extraction, the SDK for the deterministic scan + encoding. No second LLM, no Ollama dependency.
- **Cloud `encode()` call**: only the **edge list** (node names, e.g. `["frontend", "auth"]`) goes to the SemanticEmbed Railway endpoint. File contents are never sent.

If your topology is sensitive, pre-extract edges deterministically with `se.extract.from_directory()` and call `se.encode()` directly — that path sends only the edge list.

---

## Example Graphs

The `examples/` directory contains ready-to-encode edge lists and parsable
framework files. None of the `.py` examples need to be runnable — the SDK
parses them via AST without importing the framework.

**Edge-list JSON** — load with `se.encode_file(path)`:

| File | Application | Nodes | Edges |
|------|------------|-------|-------|
| [google_online_boutique.json](examples/google_online_boutique.json) | Google Online Boutique (microservices) | 11 | 15 |
| [weaveworks_sock_shop.json](examples/weaveworks_sock_shop.json) | Weaveworks Sock Shop (microservices) | 14 | 15 |
| [ai_agent_pipeline.json](examples/ai_agent_pipeline.json) | Multi-agent LLM orchestration | 12 | 15 |
| [cicd_pipeline.json](examples/cicd_pipeline.json) | CI/CD build pipeline | 12 | 17 |
| [sample_pipeline.json](examples/sample_pipeline.json) | Minimal 7-node starter | 7 | 8 |

**AI-framework Python sources** — parse with the matching extractor:

| File | Extractor | Edges |
|------|-----------|-------|
| [langgraph_research_agent.py](examples/langgraph_research_agent.py) | `from_langgraph` | 6 |
| [crewai_content_pipeline.py](examples/crewai_content_pipeline.py) | `from_crewai` | 11 |
| [autogen_codereview.py](examples/autogen_codereview.py) | `from_autogen` | 5 |

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

**Source-available, with a free tier — no signup, no credit card.** The free
tier encodes graphs up to 50 nodes; the paid tier unlocks larger graphs and
continuous monitoring. The client, parsers, and connectors in this repo are
public source, so you can read exactly what runs and what leaves your machine.

This is the same "source-available SDK, proprietary service" model Stripe,
Snowflake, and Anthropic use: the encoding algorithm runs server-side and is
patent-pending (#63/994,075), but everything in this repo is yours to read.
See [LICENSE](LICENSE) and [LICENSE-FAQ](LICENSE-FAQ.md) for terms.

**Patent pending.** Application #63/994,075.

---

## Contact

Built by **Jeff Murray** ([@jmurray10](https://github.com/jmurray10)).

- Email: **jeff.murray@alumni.upenn.edu**
- LinkedIn: [linkedin.com/in/jeff-murray-ai](https://www.linkedin.com/in/jeff-murray-ai)
- GitHub: [@jmurray10](https://github.com/jmurray10)
- License inquiries, design partnerships, and YC/investor introductions: same email.

For algorithm / encoding / scoring questions (server-side, not in this
repo): same email — please put `[encoding]` in the subject line.
