"""Live observability connectors — fetch real call edges from running infra.

Unlike :mod:`semanticembed.extract`, the functions in this module make
**outbound HTTP requests** to third-party observability APIs. Each returns
the same shape as the local extractors: ``list[tuple[str, str]]``.

For SaaS APIs that require auth, credentials may be passed explicitly or
read from the canonical environment variable for that vendor.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .extract import _dedupe


__all__ = ["from_dynatrace", "from_honeycomb", "from_datadog"]


# ---------------------------------------------------------------------------
# Dynatrace
# ---------------------------------------------------------------------------


def from_dynatrace(
    env_url: str | None = None,
    *,
    api_token: str | None = None,
    timeout: float = 30.0,
) -> list[tuple[str, str]]:
    """Fetch service-to-service call edges from a Dynatrace environment.

    Queries Smartscape (Environment API v2) for ``type("SERVICE")`` entities
    and their ``fromRelationships.calls`` references, then maps those to
    edges using each entity's ``displayName``.

    Args:
        env_url: The base URL of the Dynatrace environment, e.g.
            ``https://abc12345.live.dynatrace.com``. If omitted, falls back
            to ``DYNATRACE_ENV_URL`` from the environment.
        api_token: A Dynatrace API token with at least ``entities.read``
            scope. If omitted, falls back to ``DYNATRACE_API_TOKEN``.
        timeout: Per-request timeout in seconds.

    Returns:
        Deduplicated list of ``(source_service, target_service)`` edges.

    Raises:
        ValueError: if env_url or api_token cannot be resolved.
        httpx.HTTPStatusError: on a 4xx/5xx response from Dynatrace.

    Example::

        import semanticembed as se
        from semanticembed import live

        edges = live.from_dynatrace(
            env_url="https://abc12345.live.dynatrace.com",
            api_token=os.environ["DYNATRACE_API_TOKEN"],
        )
        result = se.encode(edges)
    """
    env_url = (env_url or os.environ.get("DYNATRACE_ENV_URL") or "").rstrip("/")
    api_token = api_token or os.environ.get("DYNATRACE_API_TOKEN")
    if not env_url:
        raise ValueError("env_url not provided and DYNATRACE_ENV_URL is unset")
    if not api_token:
        raise ValueError("api_token not provided and DYNATRACE_API_TOKEN is unset")

    headers = {"Authorization": f"Api-Token {api_token}"}
    id_to_name: dict[str, str] = {}
    entities: list[dict[str, Any]] = []

    next_page_key: str | None = None
    with httpx.Client(timeout=timeout) as client:
        while True:
            if next_page_key:
                params: dict[str, Any] = {"nextPageKey": next_page_key}
            else:
                params = {
                    "entitySelector": 'type("SERVICE")',
                    "fields": "fromRelationships.calls",
                    "pageSize": 500,
                }
            resp = client.get(
                f"{env_url}/api/v2/entities", headers=headers, params=params
            )
            resp.raise_for_status()
            data = resp.json()

            for entity in data.get("entities", []):
                eid = entity.get("entityId")
                if not eid:
                    continue
                id_to_name[eid] = entity.get("displayName", eid)
                entities.append(entity)

            next_page_key = data.get("nextPageKey")
            if not next_page_key:
                break

    edges: list[tuple[str, str]] = []
    for entity in entities:
        src = entity.get("displayName", entity.get("entityId", ""))
        calls = (entity.get("fromRelationships") or {}).get("calls", [])
        for call in calls:
            target_id = call.get("id")
            if not target_id:
                continue
            target = id_to_name.get(target_id)
            if target:
                edges.append((src, target))
    return _dedupe(edges)


# ---------------------------------------------------------------------------
# Honeycomb
# ---------------------------------------------------------------------------


def from_honeycomb(
    dataset: str | None = None,
    *,
    api_key: str | None = None,
    api_url: str = "https://api.honeycomb.io",
    lookback_seconds: int = 3600,
    max_spans: int = 10_000,
    timeout: float = 60.0,
) -> list[tuple[str, str]]:
    """Fetch service-to-service edges from a Honeycomb dataset.

    Issues a Honeycomb Query API request that breaks down spans by
    ``trace.span_id``, ``trace.parent_id``, and ``service.name`` over the
    last ``lookback_seconds``. Builds an in-memory ``span_id -> service``
    map, then emits one edge per parent-child pair where the parent and
    child are different services.

    Args:
        dataset: Honeycomb dataset slug (e.g. ``"my-app-prod"``). Falls
            back to ``HONEYCOMB_DATASET``.
        api_key: Honeycomb API key. Needs the "Run queries" permission.
            Falls back to ``HONEYCOMB_API_KEY``.
        api_url: API base. Override for EU tenants
            (``https://api.eu1.honeycomb.io``).
        lookback_seconds: Time window to query.
        max_spans: Server-side LIMIT on rows returned.
        timeout: Per-request timeout (covers both create-query and
            poll-results, separately).

    Returns:
        Deduped list of ``(parent_service, child_service)`` edges.

    Raises:
        ValueError: if dataset or api_key cannot be resolved.
        RuntimeError: if the query result polls past the timeout.
        httpx.HTTPStatusError: on a 4xx/5xx response.

    Example::

        from semanticembed import live
        edges = live.from_honeycomb(
            dataset="my-app-prod",
            api_key=os.environ["HONEYCOMB_API_KEY"],
            lookback_seconds=900,
        )
    """
    import time as _time

    dataset = dataset or os.environ.get("HONEYCOMB_DATASET")
    api_key = api_key or os.environ.get("HONEYCOMB_API_KEY")
    if not dataset:
        raise ValueError("dataset not provided and HONEYCOMB_DATASET is unset")
    if not api_key:
        raise ValueError("api_key not provided and HONEYCOMB_API_KEY is unset")

    api_url = api_url.rstrip("/")
    headers = {"X-Honeycomb-Team": api_key, "Content-Type": "application/json"}
    query_body = {
        "calculations": [{"op": "COUNT"}],
        "breakdowns": ["trace.span_id", "trace.parent_id", "service.name"],
        "filters": [{"column": "trace.span_id", "op": "exists"}],
        "filter_combination": "AND",
        "time_range": lookback_seconds,
        "limit": max_spans,
    }

    with httpx.Client(timeout=timeout) as client:
        # 1) Create the query.
        r1 = client.post(
            f"{api_url}/1/queries/{dataset}", headers=headers, json=query_body
        )
        r1.raise_for_status()
        query_id = r1.json().get("id")
        if not query_id:
            raise RuntimeError("Honeycomb create-query returned no id")

        # 2) Start the result and poll until complete.
        r2 = client.post(
            f"{api_url}/1/query_results/{dataset}",
            headers=headers,
            json={"query_id": query_id, "disable_series": True, "limit": max_spans},
        )
        r2.raise_for_status()
        result_id = r2.json().get("id")
        if not result_id:
            raise RuntimeError("Honeycomb start-result returned no id")

        deadline = _time.monotonic() + timeout
        rows: list[dict[str, Any]] = []
        while _time.monotonic() < deadline:
            r3 = client.get(
                f"{api_url}/1/query_results/{dataset}/{result_id}", headers=headers
            )
            r3.raise_for_status()
            payload = r3.json()
            if payload.get("complete"):
                rows = (payload.get("data") or {}).get("results", []) or []
                break
            _time.sleep(1.0)
        else:
            raise RuntimeError(
                f"Honeycomb query did not complete within {timeout}s"
            )

    # Honeycomb wraps each row as {"data": {breakdown: value, ...}}; unwrap for the helper.
    flat_rows = [r.get("data", r) for r in rows]
    return _edges_from_span_rows(
        flat_rows,
        span_id_key="trace.span_id",
        parent_id_key="trace.parent_id",
        service_key="service.name",
    )


# ---------------------------------------------------------------------------
# Datadog
# ---------------------------------------------------------------------------


def from_datadog(
    *,
    api_key: str | None = None,
    app_key: str | None = None,
    site: str = "datadoghq.com",
    lookback: str = "now-1h",
    max_spans: int = 1000,
    env: str | None = None,
    service: str | None = None,
    timeout: float = 30.0,
) -> list[tuple[str, str]]:
    """Fetch service-to-service edges from Datadog APM spans.

    Calls the Spans Search API (``POST /api/v2/spans/events/search``) and
    derives edges from span ``parent_id`` references. Same join logic as
    the OTEL trace parser: build a ``span_id -> service`` map, emit
    ``(parent_service, child_service)`` for each parent-child pair where
    the services differ.

    Args:
        api_key: Datadog API key. Falls back to ``DD_API_KEY`` /
            ``DATADOG_API_KEY``.
        app_key: Datadog application key (required for span search).
            Falls back to ``DD_APP_KEY`` / ``DATADOG_APP_KEY``.
        site: Datadog tenant site. Default ``datadoghq.com`` (US1). EU
            users pass ``datadoghq.eu``; US3/US5 pass ``us3.datadoghq.com``
            etc.
        lookback: Datadog relative time string for the start of the
            search window. Default ``"now-1h"``.
        max_spans: Page-size cap (Datadog enforces 1000 max per page).
        env: Optional ``env`` filter (e.g. ``"prod"``).
        service: Optional service-name filter (limits to spans whose
            ``service`` matches; useful for debugging a single service's
            upstream/downstream).
        timeout: Per-request timeout.

    Returns:
        Deduped list of ``(parent_service, child_service)`` edges.

    Raises:
        ValueError: if api_key or app_key cannot be resolved.
        httpx.HTTPStatusError: on a 4xx/5xx response.

    Example::

        from semanticembed import live
        edges = live.from_datadog(
            env="prod",
            lookback="now-30m",
        )
    """
    api_key = api_key or os.environ.get("DD_API_KEY") or os.environ.get("DATADOG_API_KEY")
    app_key = app_key or os.environ.get("DD_APP_KEY") or os.environ.get("DATADOG_APP_KEY")
    if not api_key:
        raise ValueError("api_key not provided and DD_API_KEY is unset")
    if not app_key:
        raise ValueError("app_key not provided and DD_APP_KEY is unset")

    headers = {
        "DD-API-KEY": api_key,
        "DD-APPLICATION-KEY": app_key,
        "Content-Type": "application/json",
    }

    query_parts = []
    if env:
        query_parts.append(f"env:{env}")
    if service:
        query_parts.append(f"service:{service}")
    query = " ".join(query_parts) if query_parts else "*"

    body: dict[str, Any] = {
        "data": {
            "attributes": {
                "filter": {
                    "from": lookback,
                    "to": "now",
                    "query": query,
                },
                "page": {"limit": max_spans},
                "sort": "-timestamp",
            },
            "type": "search_request",
        }
    }

    rows: list[dict[str, Any]] = []
    next_cursor: str | None = None
    fetched = 0
    with httpx.Client(timeout=timeout) as client:
        while True:
            if next_cursor:
                body["data"]["attributes"]["page"]["cursor"] = next_cursor
            resp = client.post(
                f"https://api.{site}/api/v2/spans/events/search",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            payload = resp.json()
            for ev in payload.get("data", []):
                attrs = ev.get("attributes") or {}
                rows.append({
                    "span_id": attrs.get("span_id") or ev.get("id"),
                    "parent_id": attrs.get("parent_id"),
                    "service": attrs.get("service"),
                })
                fetched += 1
            meta = payload.get("meta") or {}
            next_cursor = (meta.get("page") or {}).get("after")
            if not next_cursor or fetched >= max_spans:
                break

    return _edges_from_span_rows(
        rows, span_id_key="span_id", parent_id_key="parent_id", service_key="service"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _edges_from_span_rows(
    rows: list[dict[str, Any]],
    *,
    span_id_key: str,
    parent_id_key: str,
    service_key: str,
) -> list[tuple[str, str]]:
    """Two-pass span-row -> service-edge derivation.

    1. Build ``span_id -> service`` from every row that has both.
    2. For every row with a parent_id, look up parent's service and emit
       ``(parent_service, child_service)`` if the services differ.
    """
    span_to_service: dict[str, str] = {}
    for row in rows:
        sid = row.get(span_id_key)
        svc = row.get(service_key)
        if sid and svc:
            span_to_service[str(sid)] = str(svc)

    edges: list[tuple[str, str]] = []
    for row in rows:
        sid = row.get(span_id_key)
        pid = row.get(parent_id_key)
        if not sid or not pid:
            continue
        child_svc = span_to_service.get(str(sid))
        parent_svc = span_to_service.get(str(pid))
        if parent_svc and child_svc and parent_svc != child_svc:
            edges.append((parent_svc, child_svc))
    return _dedupe(edges)
