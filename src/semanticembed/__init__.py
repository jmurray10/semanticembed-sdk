"""SemanticEmbed SDK — 6D structural intelligence for directed graphs."""

from .client import encode, encode_file, report, drift
from .models import SemanticResult, RiskReport, RiskEntry, DIMENSION_NAMES
from .exceptions import (
    SemanticEmbedError,
    AuthenticationError,
    NodeLimitError,
    APIError,
    ConnectionError,
)

__version__ = "0.1.0"

# Set this to your license key to unlock unlimited nodes:
#   import semanticembed
#   semanticembed.license_key = "se-xxxxxxxxxxxxxxxxxxxx"
license_key: str | None = None

__all__ = [
    "encode",
    "encode_file",
    "report",
    "drift",
    "SemanticResult",
    "RiskReport",
    "RiskEntry",
    "DIMENSION_NAMES",
    "SemanticEmbedError",
    "AuthenticationError",
    "NodeLimitError",
    "APIError",
    "ConnectionError",
    "license_key",
]
