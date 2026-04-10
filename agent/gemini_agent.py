#!/usr/bin/env python3
"""
SemanticEmbed Agent (Gemini) — LLM-powered structural analysis assistant.

Same capabilities as the Claude agent, powered by Google Gemini.
Uses Gemini's function calling for tool use.

Usage:
    export GOOGLE_API_KEY=...
    python -m agent.gemini_agent
    python -m agent.gemini_agent /path/to/project
    python -m agent.gemini_agent --ask "What is my biggest SPOF?"

Requirements:
    pip install semanticembed google-genai pyyaml
"""

import json
import sys
from typing import Any

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Install google-genai: pip install google-genai")
    sys.exit(1)


# ---------------------------------------------------------------------------
# System prompt (shared with Claude agent)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the SemanticEmbed structural analysis agent. You help users understand the structural risks in their software architectures.

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


# ---------------------------------------------------------------------------
# Tool implementations (identical to Claude agent)
# ---------------------------------------------------------------------------

def _scan_directory(path: str) -> str:
    import semanticembed as se
    try:
        edges, sources = se.extract.from_directory(path)
    except Exception as e:
        return f"Error scanning: {e}"
    if not edges:
        return (f"No infrastructure files found in {path}. "
                "Try pointing to a specific file, or provide edges manually.")
    return (f"Found {len(edges)} edges from: {sources}\n\n"
            f"Edges:\n" + "\n".join(f"  {src} -> {dst}" for src, dst in edges))


def _extract_docker_compose(path: str) -> str:
    import semanticembed as se
    try:
        edges = se.extract.from_docker_compose(path)
    except Exception as e:
        return f"Error: {e}"
    return f"Extracted {len(edges)} edges:\n" + "\n".join(f"  {s} -> {d}" for s, d in edges)


def _extract_kubernetes(path: str) -> str:
    import semanticembed as se
    try:
        edges = se.extract.from_kubernetes(path)
    except Exception as e:
        return f"Error: {e}"
    return f"Extracted {len(edges)} edges:\n" + "\n".join(f"  {s} -> {d}" for s, d in edges)


def _extract_python_imports(path: str) -> str:
    import semanticembed as se
    try:
        edges = se.extract.from_python_imports(path)
    except Exception as e:
        return f"Error: {e}"
    return f"Extracted {len(edges)} module dependency edges:\n" + "\n".join(f"  {s} -> {d}" for s, d in edges)


def _encode_graph(edges_json: str) -> str:
    import semanticembed as se
    try:
        edges = json.loads(edges_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"
    try:
        result = se.encode(edges)
    except Exception as e:
        return f"Encoding error: {e}"
    return f"{result.table}\n\n{se.report(result)}"


def _encode_and_diff(edges_before_json: str, edges_after_json: str) -> str:
    import semanticembed as se
    try:
        before = json.loads(edges_before_json)
        after = json.loads(edges_after_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"
    try:
        diff = se.encode_diff(before, after, detail=True)
    except Exception as e:
        return f"Error: {e}"
    if not diff:
        return "No structural changes detected."
    lines = ["STRUCTURAL DRIFT:", ""]
    for node, deltas in diff.items():
        lines.append(f"  {node}:")
        for dim, info in deltas.items():
            lines.append(f"    {dim}: {info['before']:.3f} -> {info['after']:.3f} (delta: {info['delta']:+.3f})")
    return "\n".join(lines)


def _simulate_change(current_edges_json: str, add_edges_json: str = "[]", remove_edges_json: str = "[]") -> str:
    import semanticembed as se
    try:
        current = json.loads(current_edges_json)
        to_add = json.loads(add_edges_json)
        to_remove = json.loads(remove_edges_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"
    remove_set = {tuple(e) for e in to_remove}
    new_edges = [e for e in current if tuple(e) not in remove_set] + to_add
    try:
        diff = se.encode_diff(current, new_edges, detail=True)
        result_after = se.encode(new_edges)
    except Exception as e:
        return f"Error: {e}"
    lines = [
        f"SIMULATED CHANGE: +{len(to_add)} edges, -{len(to_remove)} edges",
        f"Before: {len(current)} edges, After: {len(new_edges)} edges",
        "", "NEW RISK REPORT:", str(se.report(result_after)),
    ]
    if diff:
        lines.extend(["", "WHAT CHANGED:"])
        for node, deltas in diff.items():
            changes = ", ".join(f"{d}: {info['before']:.3f}->{info['after']:.3f}" for d, info in deltas.items())
            lines.append(f"  {node}: {changes}")
    return "\n".join(lines)


# Tool dispatch
TOOL_HANDLERS = {
    "scan_directory": lambda args: _scan_directory(args["path"]),
    "extract_docker_compose": lambda args: _extract_docker_compose(args["path"]),
    "extract_kubernetes": lambda args: _extract_kubernetes(args["path"]),
    "extract_python_imports": lambda args: _extract_python_imports(args["path"]),
    "encode_graph": lambda args: _encode_graph(args["edges_json"]),
    "encode_and_diff": lambda args: _encode_and_diff(args["edges_before_json"], args["edges_after_json"]),
    "simulate_change": lambda args: _simulate_change(
        args["current_edges_json"],
        args.get("add_edges_json", "[]"),
        args.get("remove_edges_json", "[]"),
    ),
}


# ---------------------------------------------------------------------------
# Gemini tool declarations
# ---------------------------------------------------------------------------

TOOL_DECLARATIONS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="scan_directory",
            description="Scan a directory for infrastructure files and extract edges.",
            parameters=types.Schema(
                type="OBJECT",
                properties={"path": types.Schema(type="STRING", description="Directory path to scan")},
                required=["path"],
            ),
        ),
        types.FunctionDeclaration(
            name="extract_docker_compose",
            description="Extract service dependency edges from a docker-compose.yml file.",
            parameters=types.Schema(
                type="OBJECT",
                properties={"path": types.Schema(type="STRING", description="Path to docker-compose.yml")},
                required=["path"],
            ),
        ),
        types.FunctionDeclaration(
            name="extract_kubernetes",
            description="Extract service dependency edges from Kubernetes YAML manifests.",
            parameters=types.Schema(
                type="OBJECT",
                properties={"path": types.Schema(type="STRING", description="Path to k8s YAML directory or file")},
                required=["path"],
            ),
        ),
        types.FunctionDeclaration(
            name="extract_python_imports",
            description="Extract module dependency edges from Python import statements.",
            parameters=types.Schema(
                type="OBJECT",
                properties={"path": types.Schema(type="STRING", description="Path to Python source directory")},
                required=["path"],
            ),
        ),
        types.FunctionDeclaration(
            name="encode_graph",
            description="Run 6D structural encoding on an edge list. Edges should be a JSON array of [source, target] pairs.",
            parameters=types.Schema(
                type="OBJECT",
                properties={"edges_json": types.Schema(type="STRING", description="JSON array of [source, target] edge pairs")},
                required=["edges_json"],
            ),
        ),
        types.FunctionDeclaration(
            name="encode_and_diff",
            description="Compare two graph versions and show structural drift.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "edges_before_json": types.Schema(type="STRING", description="JSON array of before edges"),
                    "edges_after_json": types.Schema(type="STRING", description="JSON array of after edges"),
                },
                required=["edges_before_json", "edges_after_json"],
            ),
        ),
        types.FunctionDeclaration(
            name="simulate_change",
            description="Test a hypothetical architecture change by adding/removing edges.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "current_edges_json": types.Schema(type="STRING", description="JSON array of current edges"),
                    "add_edges_json": types.Schema(type="STRING", description="JSON array of edges to add"),
                    "remove_edges_json": types.Schema(type="STRING", description="JSON array of edges to remove"),
                },
                required=["current_edges_json"],
            ),
        ),
    ]),
]


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def run_agent_loop(client: genai.Client, model: str, messages: list, path: str) -> str:
    """Run the agent loop with automatic tool calling."""
    max_iterations = 10

    for _ in range(max_iterations):
        response = client.models.generate_content(
            model=model,
            contents=messages,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=TOOL_DECLARATIONS,
                temperature=0.1,
            ),
        )

        # Check if the model wants to call tools
        candidate = response.candidates[0]
        has_function_call = False

        for part in candidate.content.parts:
            if part.function_call:
                has_function_call = True
                fn_name = part.function_call.name
                fn_args = dict(part.function_call.args) if part.function_call.args else {}

                # Execute the tool
                handler = TOOL_HANDLERS.get(fn_name)
                if handler:
                    try:
                        result_text = handler(fn_args)
                    except Exception as e:
                        result_text = f"Tool error: {e}"
                else:
                    result_text = f"Unknown tool: {fn_name}"

                # Add assistant message with function call
                messages.append(candidate.content)

                # Add function response
                messages.append(
                    types.Content(
                        role="tool",
                        parts=[types.Part(function_response=types.FunctionResponse(
                            name=fn_name,
                            response={"result": result_text},
                        ))],
                    )
                )
                break  # Process one tool call at a time

        if not has_function_call:
            # Model gave a final text response
            text_parts = [p.text for p in candidate.content.parts if p.text]
            return "\n".join(text_parts)

    return "Agent reached maximum iterations."


def interactive(path: str = "."):
    """Run the agent in interactive mode."""
    import os
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Set GOOGLE_API_KEY or GEMINI_API_KEY environment variable.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    model = "gemini-2.5-flash"

    print("SemanticEmbed Agent (Gemini)")
    print("=" * 40)
    print(f"Scanning: {path}")
    print("Type 'quit' to exit.\n")

    # Initial scan
    messages = [
        types.Content(role="user", parts=[types.Part(text=(
            f"Working directory: {path}\n\n"
            "Scan this directory for infrastructure files, extract edges, "
            "run the 6D encoding, and give me a clear summary of the structural "
            "risks you find. If no infrastructure files exist, tell me what "
            "file types you looked for and suggest alternatives."
        ))]),
    ]

    result = run_agent_loop(client, model, messages, path)
    print(result)

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

        messages.append(
            types.Content(role="user", parts=[types.Part(text=user_input)])
        )
        result = run_agent_loop(client, model, messages, path)
        print(result)


def run_single(prompt: str, path: str = "."):
    """Run a single query."""
    import os
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Set GOOGLE_API_KEY or GEMINI_API_KEY environment variable.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    model = "gemini-2.5-flash"

    messages = [
        types.Content(role="user", parts=[types.Part(text=f"Working directory: {path}\n\n{prompt}")]),
    ]
    result = run_agent_loop(client, model, messages, path)
    print(result)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="SemanticEmbed Agent (Gemini)")
    parser.add_argument("path", nargs="?", default=".", help="Directory to analyze")
    parser.add_argument("--ask", "-a", type=str, default=None, help="Ask a specific question")
    parser.add_argument("--model", "-m", type=str, default="gemini-2.5-flash",
                        help="Gemini model (default: gemini-2.5-flash)")
    args = parser.parse_args()

    if args.ask:
        run_single(args.ask, args.path)
    else:
        interactive(args.path)


if __name__ == "__main__":
    main()
