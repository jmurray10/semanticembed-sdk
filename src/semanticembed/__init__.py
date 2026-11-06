"""SemanticEmbed SDK — 6D structural intelligence for directed graphs."""

from __future__ import annotations

from . import extract, live
from .client import (
    aencode,
    aencode_diff,
    aencode_file,
    clear_encode_cache,
    drift,
    encode,
    encode_diff,
    encode_file,
    report,
)
from .dedupe import dedupe_edges
from .exceptions import (
    APIError,
    AuthenticationError,
    NodeLimitError,
    SemanticConnectionError,
    SemanticEmbedError,
)
from .explain import ask, explain
from .find_edges import find_edges
from .models import DIMENSION_NAMES, RiskEntry, RiskReport, SemanticResult

__version__ = "0.7.5"

# Set this to your license key to unlock unlimited nodes:
#   import semanticembed
#   semanticembed.license_key = "se-xxxxxxxxxxxxxxxxxxxx"
license_key: str | None = None

__all__ = [
    "encode",
    "encode_file",
    "encode_diff",
    "aencode",
    "aencode_file",
    "aencode_diff",
    "report",
    "drift",
    "explain",
    "ask",
    "extract",
    "live",
    "find_edges",
    "dedupe_edges",
    "clear_encode_cache",
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
