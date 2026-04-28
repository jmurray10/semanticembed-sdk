"""SemanticEmbed SDK — 6D structural intelligence for directed graphs."""

from __future__ import annotations

from .client import encode, encode_file, report, drift, encode_diff
from .models import SemanticResult, RiskReport, RiskEntry, DIMENSION_NAMES
from .exceptions import (
    SemanticEmbedError,
    AuthenticationError,
    NodeLimitError,
    APIError,
    SemanticConnectionError,
)
from . import extract
from .dedupe import dedupe_edges
from .explain import explain, ask
from .find_edges import find_edges

__version__ = "0.3.0"

# Set this to your license key to unlock unlimited nodes:
#   import semanticembed
#   semanticembed.license_key = "se-xxxxxxxxxxxxxxxxxxxx"
license_key: str | None = None

__all__ = [
    "encode",
    "encode_file",
    "encode_diff",
    "report",
    "drift",
    "explain",
    "ask",
    "extract",
    "find_edges",
    "dedupe_edges",
    "SemanticResult",
    "RiskReport",
    "RiskEntry",
    "DIMENSION_NAMES",
    "SemanticEmbedError",
    "AuthenticationError",
    "NodeLimitError",
    "APIError",
    "SemanticConnectionError",
    "license_key",
]
