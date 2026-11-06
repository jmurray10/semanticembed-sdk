# Output Format

SemanticEmbed returns two things: the 6D encoding vectors and a structural risk report.

---

## Encoding Result

The `encode()` function returns a `SemanticResult` object.

### `result.vectors`

Dictionary mapping node names to 6D encoding vectors.

```python
for node, vector in result.vectors.items():
    print(f"{node}: {vector}")
# frontend: [0.000, 0.000, 0.000, 0.333, 0.556, 0.875]
```

Vector order: `[depth, independence, hierarchy, throughput, criticality, fanout]`. All values normalized to [0.0, 1.0].

### `result.table`

Formatted table sorted by criticality (highest first).

### `result.graph_info`

Graph metadata: `{"nodes": 11, "edges": 15, "max_depth": 3}`.

### `result.encoding_time_ms`

Wall-clock milliseconds for the HTTP request (including any retry), measured by the client. Not server compute time.

### `result.risks`

List of `RiskEntry` objects returned by the hosted service. Each has:

| Field | Type | Meaning |
|-------|------|---------|
| `node` | `str` | Flagged node name |
| `category` | `str` | One of the five categories below |
| `severity` | `str` | `critical`, `warning`, or `info` |
| `description` | `str` | Human-readable explanation from the service |
| `value` | `float` | Numeric value the service reports with the flag |

`entry.json()` returns the same fields as a dict.

### `result.nodes`, `result.dimensions(node)`, `result[node]`

```python
result.nodes                     # ['frontend', 'api-gateway', ...]
result["api-gateway"]            # [0.25, 0.5, 0.333, 0.5, 0.102, 0.667]
result.dimensions("api-gateway") # {'depth': 0.25, 'independence': 0.5, ...}
```

`result[node]` and `result.dimensions(node)` raise `KeyError` for an unknown node.

### `result.json()`

Full result as a JSON-serializable dictionary.

---

## Risk Report

```python
from semanticembed import report
risk = report(result)
print(risk)
```

### Risk Categories

The hosted service decides which nodes to flag. `category` is one of:

- `SINGLE_POINT_OF_FAILURE` -- the only option at its pipeline stage.
- `AMPLIFICATION_RISK` -- a failure here can cascade to many downstream dependents.
- `CONVERGENCE_SINK` -- many upstream services depend on this one target.
- `DEEP_BOTTLENECK` -- a choke point deep in the pipeline, hard to diagnose from edge monitoring.
- `MONITORING_GAP_CANDIDATE` -- on critical paths but not at the service edge, so it may be missing from dashboards.

### Severity Levels

Severity (`critical`, `warning`, `info`) is assigned by the hosted service.

### Programmatic Access

```python
import json

for r in risk.risks:
    print(f"{r.node}: {r.category} ({r.severity})")

amplification = risk.by_category("amplification")
print(json.dumps(risk.json(), indent=2))
```

---

## Drift Detection

```python
from semanticembed import drift
changes = drift(result_before, result_after)
```

Returns per-node, per-dimension deltas showing what changed and by how much. Only changed nodes and dimensions appear.

Pass `detail=True` to get `{"before": x, "after": y, "delta": d}` for each changed dimension instead of the delta alone:

```python
changes = drift(result_before, result_after, detail=True)
```

`encode_diff(edges_before, edges_after)` encodes both edge lists and returns the drift in one call. Its `detail` defaults to `True`.
