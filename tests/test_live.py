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
    for var in (
        "DYNATRACE_ENV_URL", "DYNATRACE_API_TOKEN",
        "HONEYCOMB_DATASET", "HONEYCOMB_API_KEY",
        "DD_API_KEY", "DD_APP_KEY", "DATADOG_API_KEY", "DATADOG_APP_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


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
        assert hasattr(se.live, "from_honeycomb")
        assert hasattr(se.live, "from_datadog")


# ---------- Honeycomb ----------------------------------------------------

HC_URL = "https://api.honeycomb.io"
DATASET = "my-app"


def _hc_row(span_id: str, parent_id: str | None, service: str) -> dict:
    return {
        "data": {
            "trace.span_id": span_id,
            "trace.parent_id": parent_id,
            "service.name": service,
            "COUNT": 1,
        }
    }


class TestHoneycomb:
    @respx.mock
    def test_builds_edges_from_span_rows(self):
        # frontend (s1) -> auth (s2) -> db (s3); same-service spans should drop.
        rows = [
            _hc_row("s1", None, "frontend"),
            _hc_row("s2", "s1", "auth"),
            _hc_row("s2b", "s2", "auth"),  # same-service: dropped
            _hc_row("s3", "s2b", "db"),
        ]
        respx.post(f"{HC_URL}/1/queries/{DATASET}").mock(
            return_value=httpx.Response(201, json={"id": "q1"})
        )
        respx.post(f"{HC_URL}/1/query_results/{DATASET}").mock(
            return_value=httpx.Response(201, json={"id": "r1"})
        )
        respx.get(f"{HC_URL}/1/query_results/{DATASET}/r1").mock(
            return_value=httpx.Response(200, json={
                "complete": True,
                "data": {"results": rows},
            })
        )
        edges = live.from_honeycomb(dataset=DATASET, api_key="hc-test")
        edges_set = {tuple(e) for e in edges}
        assert ("frontend", "auth") in edges_set
        assert ("auth", "db") in edges_set
        assert ("auth", "auth") not in edges_set

    @respx.mock
    def test_sends_team_header(self):
        route = respx.post(f"{HC_URL}/1/queries/{DATASET}").mock(
            return_value=httpx.Response(201, json={"id": "q1"})
        )
        respx.post(f"{HC_URL}/1/query_results/{DATASET}").mock(
            return_value=httpx.Response(201, json={"id": "r1"})
        )
        respx.get(f"{HC_URL}/1/query_results/{DATASET}/r1").mock(
            return_value=httpx.Response(200, json={"complete": True, "data": {"results": []}})
        )
        live.from_honeycomb(dataset=DATASET, api_key="hc-secret")
        assert route.calls.last.request.headers["X-Honeycomb-Team"] == "hc-secret"

    @respx.mock
    def test_uses_env_vars_as_fallback(self, monkeypatch):
        monkeypatch.setenv("HONEYCOMB_DATASET", DATASET)
        monkeypatch.setenv("HONEYCOMB_API_KEY", "hc-from-env")
        respx.post(f"{HC_URL}/1/queries/{DATASET}").mock(
            return_value=httpx.Response(201, json={"id": "q1"})
        )
        respx.post(f"{HC_URL}/1/query_results/{DATASET}").mock(
            return_value=httpx.Response(201, json={"id": "r1"})
        )
        route = respx.get(f"{HC_URL}/1/query_results/{DATASET}/r1").mock(
            return_value=httpx.Response(200, json={"complete": True, "data": {"results": []}})
        )
        live.from_honeycomb()
        assert route.calls.last.request.headers["X-Honeycomb-Team"] == "hc-from-env"

    def test_raises_when_dataset_missing(self):
        with pytest.raises(ValueError, match="dataset"):
            live.from_honeycomb(api_key="hc-test")

    def test_raises_when_api_key_missing(self):
        with pytest.raises(ValueError, match="api_key"):
            live.from_honeycomb(dataset=DATASET)

    @respx.mock
    def test_eu_api_url_override(self):
        eu = "https://api.eu1.honeycomb.io"
        respx.post(f"{eu}/1/queries/{DATASET}").mock(
            return_value=httpx.Response(201, json={"id": "q1"})
        )
        respx.post(f"{eu}/1/query_results/{DATASET}").mock(
            return_value=httpx.Response(201, json={"id": "r1"})
        )
        respx.get(f"{eu}/1/query_results/{DATASET}/r1").mock(
            return_value=httpx.Response(200, json={"complete": True, "data": {"results": []}})
        )
        live.from_honeycomb(dataset=DATASET, api_key="hc-eu", api_url=eu)


# ---------- Datadog ------------------------------------------------------

DD_URL = "https://api.datadoghq.com"


def _dd_event(span_id: str, parent_id: str | None, service: str) -> dict:
    return {
        "id": span_id,
        "type": "spans",
        "attributes": {
            "span_id": span_id,
            "parent_id": parent_id,
            "service": service,
        },
    }


class TestDatadog:
    @respx.mock
    def test_builds_edges_from_span_search(self):
        respx.post(f"{DD_URL}/api/v2/spans/events/search").mock(
            return_value=httpx.Response(200, json={
                "data": [
                    _dd_event("s1", None, "frontend"),
                    _dd_event("s2", "s1", "auth"),
                    _dd_event("s3", "s2", "db"),
                ],
                "meta": {"page": {}},
            })
        )
        edges = live.from_datadog(api_key="dd-key", app_key="dd-app")
        edges_set = {tuple(e) for e in edges}
        assert ("frontend", "auth") in edges_set
        assert ("auth", "db") in edges_set

    @respx.mock
    def test_paginates_via_cursor(self):
        respx.post(f"{DD_URL}/api/v2/spans/events/search").mock(
            side_effect=[
                httpx.Response(200, json={
                    "data": [_dd_event("s1", None, "frontend"), _dd_event("s2", "s1", "auth")],
                    "meta": {"page": {"after": "cursor123"}},
                }),
                httpx.Response(200, json={
                    "data": [_dd_event("s3", "s2", "db")],
                    "meta": {"page": {}},
                }),
            ]
        )
        edges = live.from_datadog(api_key="dd-key", app_key="dd-app", max_spans=5000)
        edges_set = {tuple(e) for e in edges}
        assert ("frontend", "auth") in edges_set
        assert ("auth", "db") in edges_set

    @respx.mock
    def test_sends_both_auth_headers(self):
        route = respx.post(f"{DD_URL}/api/v2/spans/events/search").mock(
            return_value=httpx.Response(200, json={"data": [], "meta": {"page": {}}})
        )
        live.from_datadog(api_key="api-secret", app_key="app-secret")
        sent = route.calls.last.request
        assert sent.headers["DD-API-KEY"] == "api-secret"
        assert sent.headers["DD-APPLICATION-KEY"] == "app-secret"

    @respx.mock
    def test_eu_site_override(self):
        eu = "https://api.datadoghq.eu"
        respx.post(f"{eu}/api/v2/spans/events/search").mock(
            return_value=httpx.Response(200, json={"data": [], "meta": {"page": {}}})
        )
        live.from_datadog(api_key="dd", app_key="dd", site="datadoghq.eu")

    @respx.mock
    def test_env_filter_in_query(self):
        route = respx.post(f"{DD_URL}/api/v2/spans/events/search").mock(
            return_value=httpx.Response(200, json={"data": [], "meta": {"page": {}}})
        )
        live.from_datadog(api_key="dd", app_key="dd", env="prod", service="api")
        body = route.calls.last.request.read().decode()
        assert "env:prod" in body
        assert "service:api" in body

    @respx.mock
    def test_uses_env_vars_as_fallback(self, monkeypatch):
        monkeypatch.setenv("DD_API_KEY", "from-env-api")
        monkeypatch.setenv("DD_APP_KEY", "from-env-app")
        route = respx.post(f"{DD_URL}/api/v2/spans/events/search").mock(
            return_value=httpx.Response(200, json={"data": [], "meta": {"page": {}}})
        )
        live.from_datadog()
        sent = route.calls.last.request
        assert sent.headers["DD-API-KEY"] == "from-env-api"
        assert sent.headers["DD-APPLICATION-KEY"] == "from-env-app"

    def test_raises_when_api_key_missing(self):
        with pytest.raises(ValueError, match="api_key"):
            live.from_datadog(app_key="dd-app")

    def test_raises_when_app_key_missing(self):
        with pytest.raises(ValueError, match="app_key"):
            live.from_datadog(api_key="dd-api")

    @respx.mock
    def test_propagates_4xx(self):
        respx.post(f"{DD_URL}/api/v2/spans/events/search").mock(
            return_value=httpx.Response(403, text="forbidden")
        )
        with pytest.raises(httpx.HTTPStatusError):
            live.from_datadog(api_key="bad", app_key="bad")
