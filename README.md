# SemanticEmbed SDK

**Structural intelligence for directed graphs. Six numbers per node. Sub-millisecond.**

SemanticEmbed computes a 6-dimensional structural encoding for every node in a directed graph. From a bare edge list -- no runtime telemetry, no historical data, no tuning -- it produces six independent measurements that fully describe each node's structural role.

---

## Try It Now

**[Open the Interactive Demo in Google Colab](https://colab.research.google.com/github/semanticembed/sdk/blob/main/notebooks/01_quickstart.ipynb)** -- runs in your browser, nothing to install locally.

---

## Install

```bash
pip install semanticembed
```

**Free tier:** Up to 50 nodes per graph. No signup required.
**Paid tier:** Unlimited nodes, continuous monitoring, CI/CD integration. [See pricing](https://semanticembed.com/pricing).

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

## Notebooks

Step-by-step Colab notebooks. Click to open, run in your browser.

| Notebook | What You Learn |
|----------|---------------|
| [01 - Quickstart](https://colab.research.google.com/github/semanticembed/sdk/blob/main/notebooks/01_quickstart.ipynb) | Install, encode a graph, read the risk report |
| [02 - Dimensions Deep Dive](https://colab.research.google.com/github/semanticembed/sdk/blob/main/notebooks/02_dimensions.ipynb) | What each of the six dimensions means, with examples |
| [03 - Drift Detection](https://colab.research.google.com/github/semanticembed/sdk/blob/main/notebooks/03_drift_detection.ipynb) | Compare two versions of a graph, detect structural changes |
| [04 - Bring Your Own Graph](https://colab.research.google.com/github/semanticembed/sdk/blob/main/notebooks/04_bring_your_own.ipynb) | Encode your own architecture from JSON, OTel, or K8s |

---

## The Six Dimensions

Every node gets six independent structural measurements:

| Dimension | What It Measures |
|-----------|-----------------|
| **Depth** | Position in the execution pipeline (0.0 = entry, 1.0 = deepest) |
| **Independence** | Lateral redundancy at the same pipeline stage |
| **Hierarchy** | Module or group membership |
| **Throughput** | Fraction of total traffic flowing through the node |
| **Criticality** | Fraction of end-to-end paths depending on this node |
| **Fanout** | Broadcaster (1.0) vs aggregator (0.0) |

These six properties are mathematically independent -- knowing any five tells you nothing about the sixth.

See [docs/dimensions.md](docs/dimensions.md) for the full reference.

---

## Example Graphs

The `examples/` directory contains edge lists for well-known architectures:

| File | Application | Nodes | Edges |
|------|------------|-------|-------|
| [google_online_boutique.json](examples/google_online_boutique.json) | Google Online Boutique | 11 | 15 |
| [weaveworks_sock_shop.json](examples/weaveworks_sock_shop.json) | Weaveworks Sock Shop | 14 | 15 |
| [sample_pipeline.json](examples/sample_pipeline.json) | Generic Data Pipeline | 10 | 10 |

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

## What It Finds That Other Tools Miss

| Your current tools | SemanticEmbed |
|---|---|
| This service has high latency | This service is on 89% of all paths (structural SPOF) |
| This service had 5 errors | This service fans out to 12 downstream services (amplification risk) |
| This service is healthy | This service has zero lateral redundancy (convergence sink) |

Runtime monitoring tells you what is slow **now**. Structural analysis tells you what **will** cause cascading failures regardless of current load.

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/dimensions.md](docs/dimensions.md) | The six structural dimensions -- full reference |
| [docs/input_format.md](docs/input_format.md) | Edge list input specification |
| [docs/output_format.md](docs/output_format.md) | Encoding output and risk report format |
| [docs/license_keys.md](docs/license_keys.md) | Activating a paid license key |

---

## License

SemanticEmbed SDK is proprietary software distributed as a compiled package.
Free tier available for graphs up to 50 nodes. See [LICENSE](LICENSE) for terms.

**Patent pending.** Application #63/994,075.

---

## Links

- [Website](https://semanticembed.com)
- [Pricing](https://semanticembed.com/pricing)
- [Contact](mailto:jeff@semanticembed.com)
