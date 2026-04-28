"""Tests for semanticembed.live (live observability connectors).

Mock the Dynatrace API with respx — no live network calls.
"""

from __future__ import annotations

import httpx
import pytest
import respx

import semanticembed as se
from semanticembed import live


ENV_URL = "https://abc12345.live.dynatrace.com"


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("DYNATRACE_ENV_URL", raising=False)
    monkeypatch.delenv("DYNATRACE_API_TOKEN", raising=False)


def _entity(eid, name, calls=None):
    return {
        "entityId": eid,
        "displayName": name,
        "fromRelationships": {"calls": [{"id": c} for c in (calls or [])]},
    }


class TestDynatrace:
    @respx.mock
    def test_builds_edges_from_calls(self):
        respx.get(f"{ENV_URL}/api/v2/entities").mock(
            return_value=httpx.Response(200, json={
                "entities": [
                    _entity("SVC-A", "frontend", calls=["SVC-B", "SVC-C"]),
                    _entity("SVC-B", "auth", calls=["SVC-D"]),
                    _entity("SVC-C", "catalog", calls=["SVC-D"]),
                    _entity("SVC-D", "db"),
                ],
            })
        )
        edges = live.from_dynatrace(env_url=ENV_URL, api_token="dt0c01.test")
        edges_set = {tuple(e) for e in edges}
        assert ("frontend", "auth") in edges_set
        assert ("frontend", "catalog") in edges_set
        assert ("auth", "db") in edges_set
        assert ("catalog", "db") in edges_set
        assert len(edges) == 4

    @respx.mock
    def test_paginates_via_next_page_key(self):
        page1 = {
            "entities": [_entity("SVC-A", "frontend", calls=["SVC-B"])],
            "nextPageKey": "PAGE2",
        }
        page2 = {
            "entities": [_entity("SVC-B", "auth")],
        }
        respx.get(f"{ENV_URL}/api/v2/entities").mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )
        edges = live.from_dynatrace(env_url=ENV_URL, api_token="dt0c01.test")
        assert ("frontend", "auth") in {tuple(e) for e in edges}

    @respx.mock
    def test_sends_api_token_header(self):
        route = respx.get(f"{ENV_URL}/api/v2/entities").mock(
            return_value=httpx.Response(200, json={"entities": []})
        )
        live.from_dynatrace(env_url=ENV_URL, api_token="dt0c01.secret")
        sent = route.calls.last.request
        assert sent.headers["Authorization"] == "Api-Token dt0c01.secret"

    @respx.mock
    def test_strips_trailing_slash_on_env_url(self):
        route = respx.get(f"{ENV_URL}/api/v2/entities").mock(
            return_value=httpx.Response(200, json={"entities": []})
        )
        live.from_dynatrace(env_url=ENV_URL + "/", api_token="dt0c01.test")
        # Should hit the URL without double-slash
        assert route.call_count == 1

    @respx.mock
    def test_uses_env_vars_as_fallback(self, monkeypatch):
        monkeypatch.setenv("DYNATRACE_ENV_URL", ENV_URL)
        monkeypatch.setenv("DYNATRACE_API_TOKEN", "dt0c01.from-env")
        route = respx.get(f"{ENV_URL}/api/v2/entities").mock(
            return_value=httpx.Response(200, json={"entities": []})
        )
        live.from_dynatrace()
        assert route.calls.last.request.headers["Authorization"] == "Api-Token dt0c01.from-env"

    def test_raises_when_env_url_missing(self):
        with pytest.raises(ValueError, match="env_url"):
            live.from_dynatrace(api_token="dt0c01.test")

    def test_raises_when_token_missing(self):
        with pytest.raises(ValueError, match="api_token"):
            live.from_dynatrace(env_url=ENV_URL)

    @respx.mock
    def test_propagates_4xx(self):
        respx.get(f"{ENV_URL}/api/v2/entities").mock(
            return_value=httpx.Response(401, text="invalid token")
        )
        with pytest.raises(httpx.HTTPStatusError):
            live.from_dynatrace(env_url=ENV_URL, api_token="bad")

    @respx.mock
    def test_drops_calls_with_unknown_target_ids(self):
        respx.get(f"{ENV_URL}/api/v2/entities").mock(
            return_value=httpx.Response(200, json={
                "entities": [
                    _entity("SVC-A", "frontend", calls=["SVC-MISSING"]),
                ],
            })
        )
        # The target SVC-MISSING isn't in the entity list, so the edge is
        # silently dropped (we can't name it).
        edges = live.from_dynatrace(env_url=ENV_URL, api_token="dt0c01.test")
        assert edges == []


class TestLiveExportedFromTopLevel:
    def test_se_live_module_is_importable(self):
        # Regression: `import semanticembed as se; se.live.from_dynatrace`
        # should work without an explicit `from semanticembed import live`.
        assert hasattr(se, "live")
        assert hasattr(se.live, "from_dynatrace")
