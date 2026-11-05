"""Shared test setup."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_retry_backoff(monkeypatch):
    """Retry paths sleep between attempts. Tests check attempts, not the wait."""
    import semanticembed.client as client
    import semanticembed.live as live

    monkeypatch.setattr(client, "_RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(live, "_RETRY_BACKOFF_SECONDS", 0)
