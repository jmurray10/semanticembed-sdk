"""SemanticEmbed SDK — 6D structural intelligence for directed graphs."""

from __future__ import annotations

from .client import (
    encode, encode_file, report, drift, encode_diff,
    aencode, aencode_file, aencode_diff,
    clear_encode_cache,
)
from .models import SemanticResult, RiskReport, RiskEntry, DIMENSION_NAMES
from .exceptions import (
    SemanticEmbedError,
    AuthenticationError,
    NodeLimitError,
    APIError,
    SemanticConnectionError,
)
from . import extract
from . import live
from .dedupe import dedupe_edges
from .explain import explain, ask
from .find_edges import find_edges

__version__ = "0.7.2"

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
