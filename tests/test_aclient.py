"""Tests for the async surface: aencode, aencode_file, aencode_diff.

Mirrors the sync test cases — preflight, retry-once, cache, error paths.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

import semanticembed as se
from semanticembed.client import DEFAULT_API_URL, FREE_TIER_LIMIT
from semanticembed.exceptions import (
    AuthenticationError,
    NodeLimitError,
    SemanticConnectionError,
)


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

SAMPLE_EDGES = [["a", "b"], ["b", "c"]]


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    se.license_key = None
    se.clear_encode_cache()
    monkeypatch.delenv("SEMANTICEMBED_LICENSE_KEY", raising=False)
    monkeypatch.delenv("SEMANTICEMBED_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTICEMBED_API_URL", raising=False)
    yield
    se.license_key = None
    se.clear_encode_cache()


def _run(coro):
    return asyncio.run(coro)


class TestAencodeHappyPath:
    @respx.mock
    def test_returns_result(self):
        respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        result = _run(se.aencode(SAMPLE_EDGES))
        assert set(result.vectors.keys()) == {"a", "b", "c"}
        assert result.graph_info["nodes"] == 3


class TestAencodePreflight:
    def test_free_tier_preflight_skips_http(self):
        edges = [[f"n{i}", f"n{i+1}"] for i in range(59)]  # 60 nodes
        with respx.mock:
            route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
                return_value=httpx.Response(200, json=VALID_BODY)
            )
            with pytest.raises(NodeLimitError) as ei:
                _run(se.aencode(edges))
            assert route.call_count == 0
        assert ei.value.n_nodes == 60


class TestAencodeRetry:
    @respx.mock
    def test_retries_once_on_503(self):
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            side_effect=[
                httpx.Response(503, text="upstream"),
                httpx.Response(200, json=VALID_BODY),
            ]
        )
        result = _run(se.aencode(SAMPLE_EDGES))
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
        result = _run(se.aencode(SAMPLE_EDGES))
        assert route.call_count == 2
        assert result is not None

    @respx.mock
    def test_does_not_retry_on_401(self):
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(401, text="invalid")
        )
        with pytest.raises(AuthenticationError):
            _run(se.aencode(SAMPLE_EDGES, license_key="bad"))
        assert route.call_count == 1


class TestAencodeCache:
    @respx.mock
    def test_cache_hit_skips_http(self):
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        r1 = _run(se.aencode(SAMPLE_EDGES, cache=True))
        r2 = _run(se.aencode(SAMPLE_EDGES, cache=True))
        assert route.call_count == 1
        assert r1 is r2

    @respx.mock
    def test_async_and_sync_share_cache(self):
        # Cache hit between sync encode -> async aencode (same edges).
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        r1 = se.encode(SAMPLE_EDGES, cache=True)
        r2 = _run(se.aencode(SAMPLE_EDGES, cache=True))
        assert route.call_count == 1
        assert r1 is r2


class TestAencodeFile:
    @respx.mock
    def test_loads_from_json_file(self, tmp_path):
        f = tmp_path / "g.json"
        f.write_text(json.dumps({"edges": [["a", "b"], ["b", "c"]]}))
        respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        result = _run(se.aencode_file(str(f)))
        assert set(result.vectors.keys()) == {"a", "b", "c"}


class TestAencodeDiff:
    @respx.mock
    def test_runs_two_encodes_in_parallel_and_returns_drift(self):
        route = respx.post(f"{DEFAULT_API_URL}/api/v1/encode").mock(
            return_value=httpx.Response(200, json=VALID_BODY)
        )
        result = _run(se.aencode_diff(
            [["a", "b"], ["b", "c"]],
            [["a", "b"], ["b", "c"], ["a", "c"]],
        ))
        # Both encodes were issued.
        assert route.call_count == 2
        # Drift returns a dict (may be empty if identical embeddings, that's fine).
        assert isinstance(result, dict)


class TestAencodeRequestValidation:
    def test_too_few_edges_raises(self):
        with pytest.raises(ValueError, match="at least 2 edges"):
            _run(se.aencode([["a", "b"]]))