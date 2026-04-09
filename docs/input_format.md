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

## Auto-Extract Edges

The `extract` module parses common infrastructure and code files directly:

```python
import semanticembed as se

edges = se.extract.from_docker_compose("docker-compose.yml")
edges = se.extract.from_kubernetes("k8s/")
edges = se.extract.from_github_actions(".github/workflows")
edges = se.extract.from_terraform("infra/")
edges = se.extract.from_python_imports("src/")
edges = se.extract.from_package_json_workspaces(".")

# Or auto-detect everything
edges, sources = se.extract.from_directory(".")
```

Requires `pyyaml`: `pip install pyyaml`

See [API Reference](api_reference.md#extract-module) for full details.

---

## Common Data Sources

| Source | How to get edges | `extract` support |
|--------|-----------------|-------------------|
| **Docker Compose** | `depends_on`, `links` | `from_docker_compose()` |
| **Kubernetes** | Service selectors, Ingress backends | `from_kubernetes()` |
| **GitHub Actions** | Job `needs` fields | `from_github_actions()` |
| **Terraform** | Resource cross-references | `from_terraform()` |
| **Python codebase** | Module import graph | `from_python_imports()` |
| **Node.js monorepo** | Inter-package dependencies | `from_package_json_workspaces()` |
| **OpenTelemetry traces** | Parent-child span relationships | See [notebook 07](https://colab.research.google.com/github/jmurray10/semanticembed-sdk/blob/main/notebooks/07_opentelemetry.ipynb) |
| **Istio / Envoy** | Service mesh call graph | Extract from proxy telemetry |
| **Static config** | Architecture diagram exported as edge list | Manual |
