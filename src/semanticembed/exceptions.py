"""SemanticEmbed SDK exceptions."""


class SemanticEmbedError(Exception):
    """Base exception for all SDK errors."""


class AuthenticationError(SemanticEmbedError):
    """Invalid or missing API key / license key."""


class NodeLimitError(SemanticEmbedError):
    """Graph exceeds the node limit for the current plan."""

    def __init__(self, n_nodes: int, limit: int):
        self.n_nodes = n_nodes
        self.limit = limit
        super().__init__(
            f"Graph has {n_nodes} nodes but your plan allows {limit}. "
            f"Contact jeffmurr@seas.upenn.edu for a license key"
        )


class APIError(SemanticEmbedError):
    """Server returned an error response."""

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"API error {status}: {detail}")


class SemanticConnectionError(SemanticEmbedError):
    """Could not connect to the SemanticEmbed API."""
