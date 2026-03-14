"""HTTP client for the SemanticEmbed cloud API."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from .exceptions import APIError, AuthenticationError, SemanticConnectionError, NodeLimitError
from .models import DIMENSION_NAMES, RiskEntry, RiskReport, SemanticResult

DEFAULT_API_URL = "https://semanticembed-api-production.up.railway.app"
FREE_TIER_LIMIT = 50


def _resolve_key(license_key: str | None) -> str:
    """Resolve the API / license key from explicit arg, module-level, env var, or config file."""
    # 1. Explicit argument
    if license_key:
        return license_key

    # 2. Module-level attribute (set by user: semanticembed.license_key = "...")
    import semanticembed
    if getattr(semanticembed, "license_key", None):
        return semanticembed.license_key

    # 3. Environment variable
    env_key = os.environ.get("SEMANTICEMBED_LICENSE_KEY") or os.environ.get("SEMANTICEMBED_API_KEY")
    if env_key:
        return env_key

    # 4. Config file
    config_path = os.path.expanduser("~/.semanticembed/license")
    if os.path.isfile(config_path):
        with open(config_path) as f:
            key = f.read().strip()
            if key:
                return key

    # 5. No key — free tier (server will enforce 50-node limit)
    return ""


def _normalize_edges(edges: Any) -> list[list[str]]:
    """Accept tuples, lists, or dicts and normalize to [[source, target], ...]."""
    normalized = []
    for e in edges:
        if isinstance(e, dict):
            src = e.get("source") or e.get("src") or e.get("from")
            tgt = e.get("target") or e.get("tgt") or e.get("to")
            if not src or not tgt:
                raise ValueError(f"Edge dict must have 'source' and 'target' keys: {e}")
            normalized.append([str(src), str(tgt)])
        elif isinstance(e, (list, tuple)) and len(e) >= 2:
            normalized.append([str(e[0]), str(e[1])])
        else:
            raise ValueError(f"Invalid edge format: {e}")
    return normalized


def _parse_response(data: dict, elapsed_ms: float) -> SemanticResult:
    """Parse the API response into SDK models."""
    raw_embeddings = data.get("embeddings", {})
    vectors: dict[str, list[float]] = {}
    for node, emb in raw_embeddings.items():
        if isinstance(emb, dict):
            vectors[node] = [emb.get(d, 0.0) for d in DIMENSION_NAMES]
        elif isinstance(emb, list):
            vectors[node] = emb[:6]
        else:
            vectors[node] = [0.0] * 6

    risks = []
    for r in data.get("risks", []):
        risks.append(RiskEntry(
            node=r.get("node", ""),
            category=r.get("type", ""),
            severity=r.get("severity", "info"),
            description=r.get("description", ""),
            value=r.get("value", 0.0),
        ))

    metadata = data.get("metadata", {})
    graph_info = {
        "nodes": metadata.get("n_nodes", len(vectors)),
        "edges": metadata.get("n_edges", 0),
        "max_depth": metadata.get("max_depth", 0),
    }

    return SemanticResult(
        vectors=vectors,
        graph_info=graph_info,
        encoding_time_ms=elapsed_ms,
        risks=risks,
    )


def encode(
    edges: list,
    *,
    license_key: str | None = None,
    api_url: str | None = None,
    timeout: float = 30.0,
) -> SemanticResult:
    """Encode a directed graph and return 6D structural coordinates.

    Args:
        edges: List of edges as tuples, lists, or dicts.
            Examples: [("A", "B"), ("B", "C")]
                      [{"source": "A", "target": "B"}]
        license_key: Optional API key. If not provided, checks env/config.
        api_url: Override the API endpoint (for testing).
        timeout: Request timeout in seconds.

    Returns:
        SemanticResult with .vectors, .table, .graph_info, .risks
    """
    normalized = _normalize_edges(edges)
    if len(normalized) < 2:
        raise ValueError("Graph must have at least 2 edges.")

    key = _resolve_key(license_key)
    url = (api_url or os.environ.get("SEMANTICEMBED_API_URL") or DEFAULT_API_URL).rstrip("/")

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if key:
        headers["X-API-Key"] = key

    # Count nodes for error reporting
    node_set = set()
    for e in normalized:
        node_set.add(e[0])
        node_set.add(e[1])

    payload = {"edges": normalized}

    start = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{url}/api/v1/encode", headers=headers, json=payload)
    except httpx.ConnectError as e:
        raise SemanticConnectionError(f"Could not connect to SemanticEmbed API at {url}: {e}") from e
    elapsed_ms = (time.perf_counter() - start) * 1000

    if resp.status_code == 401:
        raise AuthenticationError("Invalid API key. Check your license key or sign up at https://semanticembed.com")
    if resp.status_code == 403:
        detail = resp.text[:300]
        # Parse node count from detail message if possible
        import re
        match = re.search(r"(\d+) nodes.*limit.*?(\d+)", detail)
        if match:
            n_nodes = int(match.group(1))
            limit = int(match.group(2))
        else:
            n_nodes = len(node_set)
            limit = FREE_TIER_LIMIT
        raise NodeLimitError(n_nodes, limit)
    if resp.status_code >= 400:
        detail = resp.text[:200]
        raise APIError(resp.status_code, detail)

    return _parse_response(resp.json(), elapsed_ms)


def report(result: SemanticResult) -> RiskReport:
    """Generate a structural risk report from an encoding result.

    Args:
        result: A SemanticResult from encode().

    Returns:
        RiskReport with .risks, .by_category(), .by_severity()
    """
    return RiskReport(risks=result.risks)


def encode_file(
    path: str,
    *,
    license_key: str | None = None,
    api_url: str | None = None,
    timeout: float = 30.0,
) -> SemanticResult:
    """Encode a graph from a JSON file.

    The file should contain an "edges" array with objects having
    "source" and "target" fields.

    Args:
        path: Path to a JSON file.
        license_key: Optional API key.
        api_url: Override the API endpoint.
        timeout: Request timeout in seconds.

    Returns:
        SemanticResult
    """
    import json
    with open(path) as f:
        data = json.load(f)

    edges = data.get("edges", [])
    if not edges:
        raise ValueError(f"No 'edges' array found in {path}")

    return encode(edges, license_key=license_key, api_url=api_url, timeout=timeout)


def drift(
    before: SemanticResult,
    after: SemanticResult,
) -> dict[str, dict[str, float]]:
    """Compare two encoding results and return per-node, per-dimension deltas.

    Args:
        before: Encoding result from the earlier version.
        after: Encoding result from the later version.

    Returns:
        Dict mapping node names to dicts of dimension deltas.
        Positive values mean the dimension increased.
    """
    all_nodes = set(before.vectors.keys()) | set(after.vectors.keys())
    changes: dict[str, dict[str, float]] = {}

    for node in sorted(all_nodes):
        v_before = before.vectors.get(node, [0.0] * 6)
        v_after = after.vectors.get(node, [0.0] * 6)
        deltas = {}
        for i, dim in enumerate(DIMENSION_NAMES):
            delta = v_after[i] - v_before[i]
            if abs(delta) > 1e-6:
                deltas[dim] = round(delta, 4)
        if deltas:
            changes[node] = deltas

    return changes
