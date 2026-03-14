# Getting Started

Go from zero to structural risk analysis in under 2 minutes.

---

## 1. Install

```bash
pip install semanticembed
```

Requires Python 3.9+. Only dependency is `httpx`.

---

## 2. Encode Your First Graph

```python
from semanticembed import encode, report

edges = [
    ("frontend", "api-gateway"),
    ("api-gateway", "order-service"),
    ("api-gateway", "user-service"),
    ("order-service", "payment-service"),
    ("order-service", "inventory-service"),
    ("payment-service", "database"),
]

result = encode(edges)
```

That's it. `result` now contains 6D structural coordinates for every node.

---

## 3. Read the Output

### Table view

```python
print(result.table)
```

```
Node                                 Depth  Indep   Hier   Thru   Crit    Fan
-----------------------------------------------------------------------------
order-service                        0.500  0.000  0.600  0.500  0.122  0.667
api-gateway                          0.250  0.500  0.400  0.500  0.102  0.667
payment-service                      0.750  1.000  0.800  0.333  0.061  0.500
database                             1.000  0.500  1.000  0.167  0.000  0.000
frontend                             0.000  0.500  0.200  0.167  0.000  1.000
inventory-service                    0.750  0.000  0.800  0.167  0.000  0.000
user-service                         0.500  1.000  0.600  0.167  0.000  0.000
```

Sorted by criticality (highest first). All values normalized to [0.0, 1.0].

### Access individual nodes

```python
# Raw vector (list of 6 floats)
result["api-gateway"]
# [0.25, 0.5, 0.4, 0.5, 0.102, 0.667]

# Named dimensions (dict)
result.dimensions("api-gateway")
# {'depth': 0.25, 'independence': 0.5, 'hierarchy': 0.4,
#  'throughput': 0.5, 'criticality': 0.102, 'fanout': 0.667}
```

### Graph metadata

```python
result.graph_info
# {'nodes': 7, 'edges': 6, 'max_depth': 3}

result.encoding_time_ms
# 0.42
```

---

## 4. What the Numbers Mean

| Dimension | High value means | Low value means |
|-----------|-----------------|-----------------|
| **Depth** | Deep in the pipeline (backend/database) | Entry point (frontend/gateway) |
| **Independence** | Many peers at the same depth (redundant) | Only node at its depth (chokepoint) |
| **Hierarchy** | Core infrastructure layer | Orchestration/frontend layer |
| **Throughput** | High share of total request flow | Low traffic share |
| **Criticality** | On many end-to-end paths (high blast radius) | On few or no critical paths |
| **Fanout** | Broadcasts to many downstream (amplifier) | Receives from many upstream (aggregator) |

**Key risk combinations:**

- High criticality + low independence = **Structural SPOF** (only path, high blast radius)
- High fanout + high criticality = **Amplification risk** (failure multiplies)
- Low independence + low fanout = **Convergence sink** (bottleneck aggregator)
- High throughput + low independence = **Hidden bottleneck** (traffic with no backup)

---

## 5. Generate a Risk Report

```python
risk = report(result)
print(risk)
```

```
STRUCTURAL RISK REPORT
======================

SINGLE POINT OF FAILURE:
  - order-service    | high criticality (0.122) with limited redundancy

CONVERGENCE SINK:
  - database         | receiving from upstream with no downstream dependents
```

### Filter risks programmatically

```python
# By category
spofs = risk.by_category("single point of failure")
amplification = risk.by_category("amplification")

# By severity
critical = risk.by_severity("critical")
warnings = risk.by_severity("warning")

# As JSON
import json
print(json.dumps(risk.json(), indent=2))
```

---

## 6. Compare Two Versions (Drift Detection)

```python
from semanticembed import drift

# Encode before and after a change
result_before = encode(edges_v1)
result_after = encode(edges_v2)

# See what changed
changes = drift(result_before, result_after)

for node, deltas in changes.items():
    print(f"{node}:")
    for dim, delta in deltas.items():
        print(f"  {dim}: {'+' if delta > 0 else ''}{delta:.4f}")
```

Only nodes with structural changes appear. Unchanged nodes are omitted.

---

## 7. Load from a JSON File

```python
from semanticembed import encode_file

result = encode_file("my_topology.json")
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

---

## 8. Free Tier Limits

The free tier supports graphs up to **50 nodes** with no signup or API key.

If your graph exceeds 50 nodes, you'll get a `NodeLimitError`:

```python
from semanticembed import encode, NodeLimitError

try:
    result = encode(large_edges)
except NodeLimitError as e:
    print(f"Graph has {e.n_nodes} nodes, limit is {e.limit}")
```

For larger graphs, set a license key:

```python
import semanticembed
semanticembed.license_key = "se-xxxxxxxxxxxxxxxxxxxx"
```

Or via environment variable:

```bash
export SEMANTICEMBED_LICENSE_KEY=se-xxxxxxxxxxxxxxxxxxxx
```

Contact jeffmurr@seas.upenn.edu for license keys.

---

## 9. Export Results

```python
import json

# Full result as JSON
output = result.json()
with open("analysis.json", "w") as f:
    json.dump(output, f, indent=2)

# Just the vectors
for node, vector in result.vectors.items():
    print(f"{node}: {vector}")

# Just the risks
for r in result.risks:
    print(f"{r.node}: {r.category} ({r.severity})")
```

---

## Next Steps

| Notebook | What you'll learn |
|----------|------------------|
| [01 - Quickstart](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/01_quickstart.ipynb) | Full walkthrough with two real apps |
| [02 - Dimensions](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/02_dimensions.ipynb) | Deep dive into each axis |
| [03 - Drift Detection](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/03_drift_detection.ipynb) | Compare graph versions in CI/CD |
| [04 - Bring Your Own](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/04_bring_your_own.ipynb) | JSON, OTel, Kubernetes imports |
| [05 - AI Agents](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/05_ai_agent_pipelines.ipynb) | LLM pipeline risk analysis |
| [06 - CI/CD Pipelines](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/06_cicd_pipelines.ipynb) | Build and data pipeline analysis |

See [API Reference](api_reference.md) for full function documentation.
