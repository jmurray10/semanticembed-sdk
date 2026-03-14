# SemanticEmbed SDK

**Structural intelligence for directed graphs. Six numbers per node. Sub-millisecond.**

SemanticEmbed computes a 6-dimensional structural encoding for every node in a directed graph. From a bare edge list -- no runtime telemetry, no historical data, no tuning -- it produces six independent measurements that fully describe each node's structural role.

> **Validated against production incidents.** In a blind test against a live production environment (100+ services, 2,500+ incidents over 30 days), 6D structural analysis predicted ~80% of topology-relevant incidents from the call graph alone -- before any incident occurred.

---

## Why 6D?

Observability tools tell you **what broke**. SemanticEmbed tells you **what will break** -- from topology alone.

- **No agents, no instrumentation** -- just an edge list
- **Sub-millisecond** -- encodes 100+ node graphs in <1ms
- **Works on any directed graph** -- microservices, AI agent pipelines, data workflows, CI/CD
- **Mathematically independent axes** -- six dimensions, zero redundancy, each captures structural information no other metric provides

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

These six properties are mathematically independent -- knowing any five tells you nothing about the sixth.

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

---

## Example Graphs

The `examples/` directory contains edge lists for well-known architectures:

| File | Application | Nodes | Edges |
|------|------------|-------|-------|
| [google_online_boutique.json](examples/google_online_boutique.json) | Google Online Boutique | 11 | 15 |

More example graphs coming soon.

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
