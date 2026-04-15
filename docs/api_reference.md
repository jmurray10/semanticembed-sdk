# API Reference

Complete reference for the `semanticembed` Python SDK.

---

## Functions

### `encode(edges, *, license_key=None, api_url=None, timeout=60.0)`

Encode a directed graph and return 6D structural coordinates.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `edges` | `list` | required | Edge list. Accepts tuples `("A", "B")`, lists `["A", "B"]`, or dicts `{"source": "A", "target": "B"}` |
| `license_key` | `str` | `None` | API key for paid tier. If not provided, checks module attribute, env var, then config file. |
| `api_url` | `str` | `None` | Override API endpoint (for testing). Default: SemanticEmbed cloud API. |
| `timeout` | `float` | `30.0` | Request timeout in seconds. |

**Returns:** `SemanticResult`

**Raises:**

| Exception | When |
|-----------|------|
| `NodeLimitError` | Graph exceeds plan node limit (50 free, higher for paid) |
| `AuthenticationError` | Invalid or revoked API key |
| `SemanticConnectionError` | Cannot reach the API |
| `APIError` | Server returned an error |
| `ValueError` | Fewer than 2 edges or malformed edge data |

**Example:**

```python
from semanticembed import encode

result = encode([
    ("frontend", "backend"),
    ("backend", "database"),
    ("backend", "cache"),
])
```

---

### `encode_file(path, *, license_key=None, api_url=None, timeout=30.0)`

Encode a graph from a JSON file.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str` | required | Path to JSON file with `"edges"` array |
| `license_key` | `str` | `None` | API key |
| `api_url` | `str` | `None` | Override API endpoint |
| `timeout` | `float` | `30.0` | Request timeout |

**Returns:** `SemanticResult`

**JSON file format:**

```json
{
  "edges": [
    {"source": "A", "target": "B"},
    {"source": "B", "target": "C"}
  ]
}
```

---

### `report(result)`

Generate a structural risk report from an encoding result.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `result` | `SemanticResult` | Return value from `encode()` or `encode_file()` |

**Returns:** `RiskReport`

**Example:**

```python
from semanticembed import encode, report

result = encode(edges)
risk = report(result)
print(risk)                           # formatted text report
risk.by_category("amplification")     # filter by risk type
risk.by_severity("warning")           # filter by severity
risk.json()                           # JSON-serializable list
```

---

### `drift(before, after)`

Compare two encoding results and return per-node, per-dimension deltas.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `before` | `SemanticResult` | Encoding of the earlier graph version |
| `after` | `SemanticResult` | Encoding of the later graph version |

**Returns:** `dict[str, dict[str, float]]`

Dictionary mapping node names to dimension deltas. Only nodes with changes are included. Positive values mean the dimension increased.

**Example:**

```python
from semanticembed import encode, drift

v1 = encode(edges_before)
v2 = encode(edges_after)
changes = drift(v1, v2)

for node, deltas in changes.items():
    print(f"{node}: {deltas}")
# payment: {'throughput': 0.058, 'fanout': -0.167}
```

---

## Classes

### `SemanticResult`

Returned by `encode()` and `encode_file()`.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `vectors` | `dict[str, list[float]]` | Node name → 6D vector `[depth, independence, hierarchy, throughput, criticality, fanout]` |
| `graph_info` | `dict` | `{"nodes": int, "edges": int, "max_depth": int}` |
| `encoding_time_ms` | `float` | Round-trip encoding time in milliseconds |
| `risks` | `list[RiskEntry]` | Detected structural risks |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `result[node]` | `list[float]` | 6D vector for a node (subscript access) |
| `result.dimensions(node)` | `dict[str, float]` | Named dimensions: `{"depth": 0.0, "independence": 0.5, ...}` |
| `result.nodes` | `list[str]` | All node names |
| `result.table` | `str` | Formatted table sorted by criticality |
| `result.json()` | `dict` | Full result as JSON-serializable dict |

---

### `RiskReport`

Returned by `report()`.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `risks` | `list[RiskEntry]` | All detected risks |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `str(report)` | `str` | Formatted text report grouped by category |
| `report.by_category(name)` | `list[RiskEntry]` | Filter by category (case-insensitive, e.g. `"amplification"`) |
| `report.by_severity(level)` | `list[RiskEntry]` | Filter by severity (`"critical"`, `"warning"`, `"info"`) |
| `report.json()` | `list[dict]` | All risks as JSON-serializable list |

---

### `RiskEntry`

A single structural risk finding.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `node` | `str` | Affected node name |
| `category` | `str` | Risk type: `SINGLE_POINT_OF_FAILURE`, `AMPLIFICATION_RISK`, `CONVERGENCE_SINK`, `DEEP_BOTTLENECK`, `MONITORING_GAP_CANDIDATE` |
| `severity` | `str` | `"critical"`, `"warning"`, or `"info"` |
| `description` | `str` | Human-readable explanation |
| `value` | `float` | The metric value that triggered the risk |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `entry.json()` | `dict` | JSON-serializable dict |

---

## Exceptions

All exceptions inherit from `SemanticEmbedError`.

| Exception | When | Key attributes |
|-----------|------|---------------|
| `SemanticEmbedError` | Base class for all SDK errors | — |
| `NodeLimitError` | Graph exceeds node limit | `.n_nodes`, `.limit` |
| `AuthenticationError` | Invalid or missing API key | — |
| `APIError` | Server returned an error | `.status`, `.detail` |
| `SemanticConnectionError` | Cannot connect to API | — |

**Example:**

```python
from semanticembed import encode, NodeLimitError, AuthenticationError

try:
    result = encode(edges)
except NodeLimitError as e:
    print(f"Too many nodes: {e.n_nodes} > {e.limit}")
except AuthenticationError:
    print("Check your API key")
```

---

## Configuration

### License key resolution order

The SDK checks for an API key in this order:

1. **Explicit argument:** `encode(edges, license_key="se-...")`
2. **Module attribute:** `semanticembed.license_key = "se-..."`
3. **Environment variable:** `SEMANTICEMBED_LICENSE_KEY` or `SEMANTICEMBED_API_KEY`
4. **Config file:** `~/.semanticembed/license`
5. **Free tier:** No key, 50-node limit

### API URL override

For testing or self-hosted deployments:

```python
result = encode(edges, api_url="http://localhost:8000")
```

Or via environment variable:

```bash
export SEMANTICEMBED_API_URL=http://localhost:8000
```

---

## Constants

### `DIMENSION_NAMES`

```python
from semanticembed import DIMENSION_NAMES
# ["depth", "independence", "hierarchy", "throughput", "criticality", "fanout"]
```

The canonical ordering of the six dimensions. Vectors in `result.vectors` follow this order.

---

## `extract` Module

Extract edges from infrastructure and code files. Import as `se.extract` or `from semanticembed import extract`.

Requires `pyyaml` for YAML parsing: `pip install pyyaml`

### `extract.from_docker_compose(path="docker-compose.yml")`

Parse `depends_on` and `links` from a Docker Compose file.

**Returns:** `list[tuple[str, str]]`

```python
edges = se.extract.from_docker_compose("docker-compose.yml")
```

### `extract.from_kubernetes(path=".")`

Parse Service/Deployment/Ingress selectors and env var references from Kubernetes YAML.

**Parameters:** `path` — a YAML file or directory of YAML files.

**Returns:** `list[tuple[str, str]]`

```python
edges = se.extract.from_kubernetes("k8s/")
```

### `extract.from_github_actions(path=".github/workflows")`

Parse job `needs` fields from GitHub Actions workflow files.

**Returns:** `list[tuple[str, str]]`

```python
edges = se.extract.from_github_actions()
```

### `extract.from_terraform(path=".")`

Parse resource cross-references from `.tf` files.

**Returns:** `list[tuple[str, str]]`

```python
edges = se.extract.from_terraform("infra/")
```

### `extract.from_python_imports(path=".")`

Build a module dependency graph from Python import statements. Only includes edges between modules within the scanned directory.

**Returns:** `list[tuple[str, str]]`

```python
edges = se.extract.from_python_imports("src/")
```

### `extract.from_package_json(path="package.json")`

Parse `dependencies`, `devDependencies`, and `peerDependencies` from a single package.json.

**Returns:** `list[tuple[str, str]]`

```python
edges = se.extract.from_package_json("package.json")
```

### `extract.from_package_json_workspaces(path=".")`

Find inter-package dependency edges in a monorepo. Only includes edges between local workspace packages.

**Returns:** `list[tuple[str, str]]`

```python
edges = se.extract.from_package_json_workspaces(".")
```

### `extract.from_directory(path=".")`

Auto-detect and parse all recognized formats in a directory.

**Returns:** `tuple[list[tuple[str, str]], dict[str, int]]` — edges and a dict mapping source format to edge count.

```python
edges, sources = se.extract.from_directory(".")
print(f"Found {len(edges)} edges from {sources}")
# Found 23 edges from {'docker-compose': 8, 'python-imports': 15}
```

---

## Edge Input Formats

All three formats are accepted and can be mixed:

```python
# Tuples
edges = [("A", "B"), ("B", "C")]

# Lists
edges = [["A", "B"], ["B", "C"]]

# Dicts (source/target keys)
edges = [
    {"source": "A", "target": "B"},
    {"source": "B", "target": "C"},
]
```

Dict keys accepted: `source`/`src`/`from` and `target`/`tgt`/`to`.
