"""LLM-powered analysis of 6D structural encoding results.

Bring your own LLM key. The deterministic encoding runs server-side.
The LLM only sees the output (vectors, risks, graph info) — never the algorithm.

Supported providers:
    - OpenAI (gpt-4o, gpt-4o-mini, etc.)
    - Anthropic (claude-sonnet-4-5, claude-haiku-4-5, etc.)
    - Ollama (local models, no API key needed)
"""

from __future__ import annotations

from typing import Any

from .models import DIMENSION_NAMES, SemanticResult, RiskReport


# ---------------------------------------------------------------------------
# System prompt — gives the LLM context about what 6D means
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a structural architecture analyst. You interpret 6D semantic encoding results from SemanticEmbed.

The encoding computes six structural properties per node in a directed graph:
- Depth (0-1): Pipeline position. 0=entry point, 1=deepest backend.
- Independence (0-1): Lateral redundancy. 0=only node at its depth (chokepoint). 1=many peers.
- Hierarchy (0-1): Community/module membership. Similar values = same cluster.
- Throughput (0-1): Share of total traffic flow through this node.
- Criticality (0-1): Fraction of end-to-end paths depending on this node. Higher = more paths break if it fails.
- Fanout (0-1): 1=broadcasts to many downstream. 0=aggregates from many upstream.

Risk patterns:
- SPOF: Low independence + high criticality = only path, high blast radius
- Amplification: High fanout + high criticality = failure multiplies downstream
- Convergence sink: Low independence + low fanout = bottleneck aggregator
- Deep bottleneck: High depth + high criticality = hard to diagnose from edge
- Monitoring gap: High criticality but not at service edge = likely missing from dashboards

Be specific. Reference node names and actual values. Suggest concrete fixes (add fallback, add cache, add circuit breaker, split service, add retry). Keep answers concise and actionable."""


def _format_result_for_llm(result: SemanticResult) -> str:
    """Format encoding results as context for the LLM."""
    lines = [
        f"Graph: {result.graph_info.get('nodes', 0)} nodes, "
        f"{result.graph_info.get('edges', 0)} edges, "
        f"max depth {result.graph_info.get('max_depth', 0)}",
        "",
        "6D Encoding:",
    ]

    # Sort by criticality
    ranked = sorted(result.vectors.items(), key=lambda x: x[1][4], reverse=True)
    for node, vec in ranked:
        dims = dict(zip(DIMENSION_NAMES, vec))
        lines.append(
            f"  {node}: depth={dims['depth']:.3f} indep={dims['independence']:.3f} "
            f"hier={dims['hierarchy']:.3f} thru={dims['throughput']:.3f} "
            f"crit={dims['criticality']:.3f} fan={dims['fanout']:.3f}"
        )

    # Add risk report
    report = RiskReport(risks=result.risks)
    if result.risks:
        lines.append("")
        lines.append(str(report))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _call_openai(
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    **kwargs: Any,
) -> str:
    """Call OpenAI-compatible API."""
    import httpx

    url = kwargs.get("api_url", "https://api.openai.com/v1")
    resp = httpx.post(
        f"{url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "max_tokens": 2000},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_anthropic(
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    **kwargs: Any,
) -> str:
    """Call Anthropic API."""
    import httpx

    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msgs = [m for m in messages if m["role"] != "system"]

    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 2000,
            "system": system,
            "messages": user_msgs,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def _call_ollama(
    messages: list[dict[str, str]],
    model: str,
    **kwargs: Any,
) -> str:
    """Call local Ollama instance."""
    import httpx

    url = kwargs.get("api_url", "http://localhost:11434")
    resp = httpx.post(
        f"{url}/api/chat",
        json={"model": model, "messages": messages, "stream": False},
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _resolve_provider(model: str) -> str:
    """Determine provider from model name."""
    m = model.lower()
    if m.startswith("ollama/") or m.startswith("local/"):
        return "ollama"
    if "claude" in m or "anthropic" in m:
        return "anthropic"
    # Default to OpenAI-compatible
    return "openai"


def _call_llm(
    messages: list[dict[str, str]],
    model: str,
    api_key: str | None = None,
    **kwargs: Any,
) -> str:
    """Route to the correct provider."""
    provider = kwargs.pop("provider", None) or _resolve_provider(model)

    if provider == "ollama":
        clean_model = model.replace("ollama/", "").replace("local/", "")
        return _call_ollama(messages, clean_model, **kwargs)
    elif provider == "anthropic":
        if not api_key:
            raise ValueError("Anthropic API key required. Pass api_key='sk-ant-...'")
        return _call_anthropic(messages, model, api_key, **kwargs)
    else:
        if not api_key:
            raise ValueError("OpenAI API key required. Pass api_key='sk-...'")
        return _call_openai(messages, model, api_key, **kwargs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def explain(
    result: SemanticResult,
    *,
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    prompt: str | None = None,
    **kwargs: Any,
) -> str:
    """Get an LLM-powered analysis of 6D structural encoding results.

    The LLM sees only the encoding output (vectors, risks, graph info).
    It never sees the encoding algorithm.

    Args:
        result: SemanticResult from encode().
        model: LLM model name. Prefixes determine provider:
            - "gpt-4o", "gpt-4o-mini" → OpenAI
            - "claude-sonnet-4-5", "claude-haiku-4-5" → Anthropic
            - "ollama/llama3", "ollama/mistral" → local Ollama
        api_key: API key for the chosen provider (not needed for Ollama).
        prompt: Custom analysis prompt. Default asks for a full structural analysis.
        **kwargs: Extra options (api_url for custom endpoints).

    Returns:
        Natural language analysis as a string.

    Example::

        result = se.encode(edges)
        print(se.explain(result, model="gpt-4o-mini", api_key="sk-..."))
    """
    context = _format_result_for_llm(result)

    user_prompt = prompt or (
        "Analyze this architecture's structural risks. For each risk:\n"
        "1. What is the risk and why does it matter?\n"
        "2. What specific nodes are involved (reference their 6D values)?\n"
        "3. What concrete change would fix or reduce the risk?\n"
        "Be concise and actionable."
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"{context}\n\n{user_prompt}"},
    ]

    return _call_llm(messages, model, api_key, **kwargs)


def ask(
    result: SemanticResult,
    question: str,
    *,
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    history: list[dict[str, str]] | None = None,
    **kwargs: Any,
) -> str:
    """Ask a question about the structural analysis results.

    Supports follow-up questions by passing conversation history.

    Args:
        result: SemanticResult from encode().
        question: The question to ask.
        model: LLM model name (same format as explain()).
        api_key: API key for the chosen provider.
        history: Previous Q&A pairs for context. List of
            {"role": "user"|"assistant", "content": "..."} dicts.
        **kwargs: Extra options.

    Returns:
        Answer as a string.

    Example::

        result = se.encode(edges)
        answer = se.ask(result, "What happens if the database goes down?",
                        model="gpt-4o-mini", api_key="sk-...")
    """
    context = _format_result_for_llm(result)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"Here is the structural analysis:\n\n{context}"},
        {"role": "assistant", "content": "I have the structural analysis. What would you like to know?"},
    ]

    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": question})

    return _call_llm(messages, model, api_key, **kwargs)
