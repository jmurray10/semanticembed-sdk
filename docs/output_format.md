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

Encoding time in milliseconds.

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

- **Amplification risk** -- high fanout + high criticality
- **Convergence sink** -- low independence + low fanout
- **Structural SPOF** -- low independence + high criticality
- **Hidden bottleneck** -- high throughput + low independence

### Severity Levels

- **critical** -- structural single point of failure or monitoring gap
- **warning** -- amplification risk, deep bottleneck, or high fanout
- **info** -- convergence sink or low-risk structural note

### Programmatic Access

```python
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

Returns per-node, per-dimension deltas showing what changed and by how much.
