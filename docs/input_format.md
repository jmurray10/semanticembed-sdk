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

**Required:** `edges` array with `source` and `target` string fields.

**Optional:** `name`, `description`.

---

## Requirements

- Directed acyclic graph (DAG). Cycles are automatically broken.
- Minimum 3 nodes for meaningful analysis.
- Free tier: 50 nodes max. Paid tier: unlimited.
- Node names: unique strings.
- Self-loops and duplicate edges are handled automatically.

---

## Common Data Sources

| Source | How to get edges |
|--------|-----------------|
| **OpenTelemetry traces** | Parent-child span relationships |
| **Kubernetes** | Service-to-service network policies or observed traffic |
| **Istio / Envoy** | Service mesh call graph from proxy telemetry |
| **Terraform** | Resource dependency graph |
| **Static config** | Architecture diagram exported as edge list |
| **API gateway logs** | Request routing paths |
