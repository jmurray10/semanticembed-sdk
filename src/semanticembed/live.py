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


__all__ = ["from_dynatrace"]


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
