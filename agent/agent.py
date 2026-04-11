#!/usr/bin/env python3
"""
SemanticEmbed Agent — LLM-powered structural analysis assistant.

An autonomous agent that scans your codebase, extracts service dependencies,
runs 6D structural encoding, and explains the results in plain language.

The agent uses deterministic 6D encoding (server-side, proprietary) for the
structural math, and an LLM (your key) for interpretation and conversation.

Usage:
    # Set your Anthropic API key
    export ANTHROPIC_API_KEY=sk-ant-...

    # Run the agent on current directory
    python -m semanticembed.agent

    # Run on a specific path
    python -m semanticembed.agent /path/to/project

    # Ask a specific question
    python -m semanticembed.agent --ask "What is my biggest SPOF?"

Requirements:
    pip install semanticembed claude-agent-sdk pyyaml
"""

import asyncio
import json
import sys
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ResultMessage,
    create_sdk_mcp_server,
    query,
    tool,
)


# ---------------------------------------------------------------------------
# Tools — the agent can call these autonomously
# ---------------------------------------------------------------------------

@tool(
    "scan_directory",
    "Scan a directory for infrastructure files (docker-compose, k8s, terraform, "
    "GitHub Actions, Python imports, package.json) and extract service dependency "
    "edges. Returns the edge list and which sources were found.",
    {"path": str},
)
async def scan_directory(args: dict[str, Any]) -> dict[str, Any]:
    import semanticembed as se

    path = args.get("path", ".")
    try:
        edges, sources = se.extract.from_directory(path)
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error scanning: {e}"}], "is_error": True}

    if not edges:
        return {"content": [{"type": "text", "text":
            f"No infrastructure files found in {path}. "
            "Try pointing to a specific file, or provide edges manually with add_edges."}]}

    result_text = (
        f"Found {len(edges)} edges from: {sources}\n\n"
        f"Edges:\n" + "\n".join(f"  {src} -> {dst}" for src, dst in edges)
    )
    return {"content": [{"type": "text", "text": result_text}]}


@tool(
    "extract_docker_compose",
    "Extract service dependency edges from a docker-compose.yml file.",
    {"path": str},
)
async def extract_docker_compose(args: dict[str, Any]) -> dict[str, Any]:
    import semanticembed as se

    try:
        edges = se.extract.from_docker_compose(args["path"])
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}

    return {"content": [{"type": "text", "text":
        f"Extracted {len(edges)} edges:\n" + "\n".join(f"  {s} -> {d}" for s, d in edges)}]}


@tool(
    "extract_kubernetes",
    "Extract service dependency edges from Kubernetes YAML manifests.",
    {"path": str},
)
async def extract_kubernetes(args: dict[str, Any]) -> dict[str, Any]:
    import semanticembed as se

    try:
        edges = se.extract.from_kubernetes(args["path"])
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}

    return {"content": [{"type": "text", "text":
        f"Extracted {len(edges)} edges:\n" + "\n".join(f"  {s} -> {d}" for s, d in edges)}]}


@tool(
    "extract_python_imports",
    "Extract module dependency edges from Python import statements in a codebase.",
    {"path": str},
)
async def extract_python_imports(args: dict[str, Any]) -> dict[str, Any]:
    import semanticembed as se

    try:
        edges = se.extract.from_python_imports(args["path"])
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}

    return {"content": [{"type": "text", "text":
        f"Extracted {len(edges)} module dependency edges:\n" +
        "\n".join(f"  {s} -> {d}" for s, d in edges)}]}


@tool(
    "encode_graph",
    "Run 6D structural encoding on an edge list. Returns per-node embeddings "
    "and structural risk report. The edge list should be a JSON array of "
    "[source, target] pairs.",
    {"edges_json": str},
)
async def encode_graph(args: dict[str, Any]) -> dict[str, Any]:
    import semanticembed as se

    try:
        edges = json.loads(args["edges_json"])
    except json.JSONDecodeError as e:
        return {"content": [{"type": "text", "text": f"Invalid JSON: {e}"}], "is_error": True}

    try:
        result = se.encode(edges)
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Encoding error: {e}"}], "is_error": True}

    output = f"{result.table}\n\n{se.report(result)}"
    return {"content": [{"type": "text", "text": output}]}


@tool(
    "encode_and_diff",
    "Encode two versions of a graph and show what changed structurally. "
    "Both inputs should be JSON arrays of [source, target] pairs.",
    {"edges_before_json": str, "edges_after_json": str},
)
async def encode_and_diff(args: dict[str, Any]) -> dict[str, Any]:
    import semanticembed as se

    try:
        before = json.loads(args["edges_before_json"])
        after = json.loads(args["edges_after_json"])
    except json.JSONDecodeError as e:
        return {"content": [{"type": "text", "text": f"Invalid JSON: {e}"}], "is_error": True}

    try:
        diff = se.encode_diff(before, after, detail=True)
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}

    if not diff:
        return {"content": [{"type": "text", "text": "No structural changes detected."}]}

    lines = ["STRUCTURAL DRIFT:", ""]
    for node, deltas in diff.items():
        lines.append(f"  {node}:")
        for dim, info in deltas.items():
            lines.append(f"    {dim}: {info['before']:.3f} -> {info['after']:.3f} (delta: {info['delta']:+.3f})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "simulate_change",
    "Test a hypothetical architecture change. Takes the current edges (JSON array) "
    "and a description of the change (add/remove edges), applies it, and shows "
    "the structural impact.",
    {"current_edges_json": str, "add_edges_json": str, "remove_edges_json": str},
)
async def simulate_change(args: dict[str, Any]) -> dict[str, Any]:
    import semanticembed as se

    try:
        current = json.loads(args["current_edges_json"])
        to_add = json.loads(args.get("add_edges_json", "[]"))
        to_remove = json.loads(args.get("remove_edges_json", "[]"))
    except json.JSONDecodeError as e:
        return {"content": [{"type": "text", "text": f"Invalid JSON: {e}"}], "is_error": True}

    # Build new edge list
    remove_set = {tuple(e) for e in to_remove}
    new_edges = [e for e in current if tuple(e) not in remove_set] + to_add

    try:
        diff = se.encode_diff(current, new_edges, detail=True)
        result_after = se.encode(new_edges)
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}

    lines = [
        f"SIMULATED CHANGE: +{len(to_add)} edges, -{len(to_remove)} edges",
        f"Before: {len(current)} edges, After: {len(new_edges)} edges",
        "",
        "NEW RISK REPORT:",
        str(se.report(result_after)),
    ]

    if diff:
        lines.extend(["", "WHAT CHANGED:"])
        for node, deltas in diff.items():
            changes = ", ".join(
                f"{d}: {info['before']:.3f}->{info['after']:.3f}"
                for d, info in deltas.items()
            )
            lines.append(f"  {node}: {changes}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------

AGENT_SYSTEM = """You are the SemanticEmbed structural analysis agent. You help users understand the structural risks in their software architectures.

Your workflow:
1. SCAN the user's project directory to find infrastructure files (docker-compose, k8s, terraform, Python imports, etc.)
2. EXTRACT edges from whatever files you find
3. ENCODE the graph using the 6D structural encoding
4. EXPLAIN the results — what the risks mean, which nodes matter, what to fix
5. SIMULATE changes if the user asks "what if" questions

Key principles:
- Always start by scanning the directory unless the user provides edges directly
- Explain results in plain language, not just numbers
- When you find risks, suggest specific fixes (add fallback, add cache, add circuit breaker)
- If the user asks "what if I add X?", use simulate_change to show the structural impact
- The 6D encoding is deterministic and proprietary — you don't need to explain how it works, just what it means

The six dimensions:
- Depth: pipeline position (0=entry, 1=deepest)
- Independence: lateral redundancy (0=chokepoint, 1=many peers)
- Hierarchy: community/module membership
- Throughput: share of total traffic flow
- Criticality: fraction of paths depending on this node
- Fanout: broadcaster (1) vs aggregator (0)"""


def create_server():
    """Create the MCP server with all tools."""
    return create_sdk_mcp_server(
        name="semanticembed",
        version="0.2.0",
        tools=[
            scan_directory,
            extract_docker_compose,
            extract_kubernetes,
            extract_python_imports,
            encode_graph,
            encode_and_diff,
            simulate_change,
        ],
    )


async def run_agent(prompt: str, path: str = "."):
    """Run the agent with a given prompt."""
    server = create_server()

    options = ClaudeAgentOptions(
        model="sonnet",
        system_prompt=AGENT_SYSTEM,
        mcp_servers={"semanticembed": server},
        allowed_tools=["mcp__semanticembed__*"],
    )

    full_prompt = f"Working directory: {path}\n\n{prompt}"

    async for message in query(prompt=full_prompt, options=options):
        if isinstance(message, ResultMessage) and message.subtype == "success":
            print(message.result.encode("utf-8", errors="replace").decode("utf-8"))


async def interactive(path: str = "."):
    """Run the agent in interactive mode."""
    server = create_server()

    options = ClaudeAgentOptions(
        model="sonnet",
        system_prompt=AGENT_SYSTEM,
        mcp_servers={"semanticembed": server},
        allowed_tools=["mcp__semanticembed__*"],
    )

    print("SemanticEmbed Agent")
    print("=" * 40)
    print(f"Scanning: {path}")
    print("Type 'quit' to exit.\n")

    def _print_safe(text: str) -> None:
        print(text.encode("utf-8", errors="replace").decode("utf-8"))

    # Initial scan
    initial_prompt = (
        f"Working directory: {path}\n\n"
        "Scan this directory for infrastructure files, extract edges, "
        "run the 6D encoding, and give me a clear summary of the structural "
        "risks you find. If no infrastructure files exist, tell me what "
        "file types you looked for and suggest alternatives."
    )

    async for message in query(prompt=initial_prompt, options=options):
        if isinstance(message, ResultMessage) and message.subtype == "success":
            _print_safe(message.result)

    # Follow-up loop
    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue

        async for message in query(
            prompt=f"Working directory: {path}\n\n{user_input}",
            options=options,
        ):
            if isinstance(message, ResultMessage) and message.subtype == "success":
                _print_safe(message.result)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="SemanticEmbed Agent — LLM-powered structural analysis"
    )
    parser.add_argument(
        "path", nargs="?", default=".",
        help="Directory to analyze (default: current directory)"
    )
    parser.add_argument(
        "--ask", "-a", type=str, default=None,
        help="Ask a specific question (non-interactive mode)"
    )
    args = parser.parse_args()

    if args.ask:
        asyncio.run(run_agent(args.ask, args.path))
    else:
        asyncio.run(interactive(args.path))


if __name__ == "__main__":
    main()
