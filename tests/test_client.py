"""Tests for semanticembed.client.

Mock the Railway endpoint with respx — no live network. Coverage:
- Happy path: encode returns a SemanticResult
- Pre-flight free-tier guard: >50 nodes without key raises NodeLimitError WITHOUT an HTTP call
- License key resolution (env var, explicit arg, module attr)
- Retry once on 503 / ConnectError
- 401 propagates (no retry)
"""

from __future__ import annotations

import httpx
import pytest
import respx

import semanticembed as se
from semanticembed.exceptions import (
    AuthenticationError,
    NodeLimitError,
    SemanticConnectionError,
)
from semanticembed.client import DEFAULT_API_URL, FREE_TIER_LIMIT


VALID_BODY = {
    "embeddings": {
        "a": {"depth": 0.0, "independence": 0.5, "hierarchy": 0.5,
              "throughput": 0.5, "criticality": 0.5, "fanout": 1.0},
        "b": {"depth": 0.5, "independence": 0.5, "hierarchy": 0.5,
              "throughput": 0.5, "criticality": 0.5, "fanout": 0.5},
        "c": {"depth": 1.0, "independence": 0.5, "hierarchy": 0.5,
              "throughput": 0.5, "criticality": 0.5, "fanout": 0.0},
    },
    "risks": [],
    "fingerprint": {},
    "metadata": {"n_nodes": 3, "n_edges": 2, "max_depth": 2},
}


@pytest.fixture(autouse=True)
def _reset_module_key():
    """Some tests set se.license_key — make sure each test starts clean."""
    se.license_key = None
    yield
    se.license_key = None


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("SEMANTICEMBED_LICENSE_KEY", raising=False)
    monkeypatch.delenv("SEMANTICEMBED_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTICEMBED_API_URL", raising=False)


SAMPLE_EDGES = [["a", "b"], ["b", "c"]]


class TestHappyPath:
    @respx.mock
    def test_encode_returns_result(self):
        respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        result = se.encode(SAMPLE_EDGES)
        assert set(result.vectors.keys()) == {"a", "b", "c"}
        assert result.graph_info["nodes"] == 3


class TestPreflight:
    def test_free_tier_preflight_raises_without_http_call(self):
        # 60-node chain: no key, exceeds the 50-node free tier.
        edges = [[f"n{i}", f"n{i+1}"] for i in range(59)]  # 60 unique nodes
        with respx.mock:
            route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
                return_value=httpx.Response(200, json=VALID_BODY)
            )
            with pytest.raises(NodeLimitError) as ei:
                se.encode(edges)
            # The point: no HTTP call was issued.
            assert route.call_count == 0
        assert ei.value.n_nodes == 60
        assert ei.value.limit == FREE_TIER_LIMIT

    @respx.mock
    def test_with_key_skips_preflight(self):
        # Same 60-node chain WITH a license key — preflight should not block,
        # request goes through. (Server-side cap is then up to the API tier.)
        edges = [[f"n{i}", f"n{i+1}"] for i in range(59)]
        respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        result = se.encode(edges, license_key="se-test-key")
        assert result is not None


class TestKeyResolution:
    @respx.mock
    def test_explicit_arg_sets_header(self):
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        se.encode(SAMPLE_EDGES, license_key="se-explicit-arg")
        sent = route.calls.last.request
        assert sent.headers["X-API-Key"] == "se-explicit-arg"

    @respx.mock
    def test_env_var_sets_header(self, monkeypatch):
        monkeypatch.setenv("SEMANTICEMBED_LICENSE_KEY", "se-from-env")
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        se.encode(SAMPLE_EDGES)
        assert route.calls.last.request.headers["X-API-Key"] == "se-from-env"

    @respx.mock
    def test_explicit_arg_overrides_env(self, monkeypatch):
        monkeypatch.setenv("SEMANTICEMBED_LICENSE_KEY", "se-env")
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        se.encode(SAMPLE_EDGES, license_key="se-arg-wins")
        assert route.calls.last.request.headers["X-API-Key"] == "se-arg-wins"


class TestRetry:
    @respx.mock
    def test_retries_once_on_503_then_succeeds(self):
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            side_effect=[
                httpx.Response(503, text="upstream unavailable"),
                httpx.Response(200, json=VALID_BODY),
            ]
        )
        result = se.encode(SAMPLE_EDGES)
        assert route.call_count == 2
        assert result is not None

    @respx.mock
    def test_retries_once_on_connect_error(self):
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            side_effect=[
                httpx.ConnectError("dns fail"),
                httpx.Response(200, json=VALID_BODY),
            ]
        )
        result = se.encode(SAMPLE_EDGES)
        assert route.call_count == 2
        assert result is not None

    @respx.mock
    def test_does_not_retry_on_401(self):
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(401, text="invalid key")
        )
        with pytest.raises(AuthenticationError):
            se.encode(SAMPLE_EDGES, license_key="bad-key")
        assert route.call_count == 1

    @respx.mock
    def test_persistent_503_eventually_raises(self):
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(503, text="still down")
        )
        # After 1 retry both attempts return 503 — the second one is
        # surfaced (APIError), not silently swallowed.
        with pytest.raises(Exception) as ei:
            se.encode(SAMPLE_EDGES)
        # We don't care which exact subclass, but it must surface the failure.
        assert "503" in str(ei.value) or "still down" in str(ei.value)
        assert route.call_count == 2


class TestEncodeCache:
    def setup_method(self):
        se.clear_encode_cache()

    @respx.mock
    def test_cache_disabled_by_default(self):
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        se.encode(SAMPLE_EDGES)
        se.encode(SAMPLE_EDGES)
        # No cache -> two HTTP calls.
        assert route.call_count == 2

    @respx.mock
    def test_cache_hit_skips_http(self):
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        r1 = se.encode(SAMPLE_EDGES, cache=True)
        r2 = se.encode(SAMPLE_EDGES, cache=True)
        assert route.call_count == 1
        # Identity isn't required, but the parsed object should be the same instance.
        assert r1 is r2

    @respx.mock
    def test_cache_is_order_independent(self):
        respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        r1 = se.encode([["a", "b"], ["b", "c"]], cache=True)
        r2 = se.encode([["b", "c"], ["a", "b"]], cache=True)
        assert r1 is r2

    @respx.mock
    def test_cache_distinct_edge_sets_dont_collide(self):
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        se.encode([["a", "b"], ["b", "c"]], cache=True)
        se.encode([["a", "b"], ["b", "d"]], cache=True)
        # Different edge sets -> two HTTP calls.
        assert route.call_count == 2

    @respx.mock
    def test_clear_encode_cache(self):
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        se.encode(SAMPLE_EDGES, cache=True)
        se.clear_encode_cache()
        se.encode(SAMPLE_EDGES, cache=True)
        assert route.call_count == 2


class TestServerNodeLimit:
    @respx.mock
    def test_server_403_translates_to_node_limit_error(self):
        # Even with a key, server can return 403 (e.g. bigger graph than tier allows).
        respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(
                403,
                text="Graph has 200 nodes, limit is 100. Provide an API key for higher limits.",
            )
        )
        with pytest.raises(NodeLimitError) as ei:
            se.encode(SAMPLE_EDGES, license_key="se-test-key")
        assert ei.value.n_nodes == 200
        assert ei.value.limit == 100
