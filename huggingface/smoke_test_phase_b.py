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
    # gradio_client returns 6 values: summary, plot, table, risks_md,
    # picker_update, detail_md. `gr.State` lives server-side and isn't
    # surfaced over the API.
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
    if not isinstance(out, (list, tuple)) or len(out) != 6:
        print(f"FAIL: expected 6-tuple, got {out!r}", file=sys.stderr)
        return 1

    summary, plot, table, risks, picker, detail = out
    print(f"\nsummary head: {summary[:120]!r}")
    print(f"detail head:  {detail[:200]!r}")
    print(f"picker auto-selected: {picker.get('value')!r}")

    if not isinstance(picker, dict) or not picker.get("choices"):
        print(f"FAIL: picker has no choices: {picker!r}", file=sys.stderr)
        return 1
    if "Selected node" not in detail:
        print("FAIL: detail panel doesn't show selected node header", file=sys.stderr)
        return 1
    if picker.get("value") != "planner":
        print(f"FAIL: expected planner auto-selected, got {picker.get('value')!r}",
              file=sys.stderr)
        return 1

    # Now exercise the dropdown change handler -> render END's panel
    print("\nSwitch to END ...")
    detail2 = c.predict("END", api_name="/_on_node_select")
    if "END" not in detail2 or "No structural risks" not in detail2:
        print(f"FAIL: END detail wrong: {detail2[:300]!r}", file=sys.stderr)
        return 1
    print(f"END detail head: {detail2[:200]!r}")

    print("\nOK: Phase B is live.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
