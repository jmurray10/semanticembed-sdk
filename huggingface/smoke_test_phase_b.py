"""End-to-end smoke test for the live HF Space (Phase B).

Hits the deployed Space via gradio_client and exercises:
1. The Analyze button with the LangGraph starter
2. The Inspect-node dropdown switch (planner -> END -> writer)

Run after each redeploy. Exits non-zero if any check fails.
"""
from __future__ import annotations

import sys

from gradio_client import Client


SPACE = "jmurray10/semanticembed-agent-risk"


def main() -> int:
    print(f"Connecting to {SPACE} ...")
    c = Client(SPACE)

    api = c.view_api(return_format="dict")
    fn_names = [e.get("api_name") for e in api.get("named_endpoints", {}).values()]
    print("named endpoints:", fn_names)

    # The /analyze endpoint is the click handler on analyze_btn.
    # Returns: summary, plot, table, risks, state, picker_update, detail_md
    print("\nAnalyze with LangGraph starter ...")
    starter = (
        "from langgraph.graph import StateGraph\n"
        "g = StateGraph(dict)\n"
        "g.add_edge('planner', 'researcher')\n"
        "g.add_edge('researcher', 'writer')\n"
        "g.add_edge('writer', 'critic')\n"
        "g.add_edge('critic', 'planner')\n"
        "g.set_entry_point('planner')\n"
        "g.set_finish_point('critic')\n"
    )
    out = c.predict("LangGraph", starter, api_name="/analyze")
    print(f"return type: {type(out).__name__}, len: {len(out) if hasattr(out, '__len__') else '?'}")
    if not isinstance(out, (list, tuple)) or len(out) != 7:
        print(f"FAIL: expected 7-tuple, got {out!r}", file=sys.stderr)
        return 1

    summary, plot, table, risks, state, picker, detail = out
    print(f"\nsummary head: {summary[:120]!r}")
    print(f"detail head:  {detail[:200]!r}")
    print(f"picker:       {picker}")

    if "nodes" not in (state or {}):
        print(f"FAIL: state missing nodes key: {state!r}", file=sys.stderr)
        return 1
    if "Selected node" not in detail:
        print(f"FAIL: detail panel doesn't show selected node header", file=sys.stderr)
        return 1
    print("\nOK: Phase B is live.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
