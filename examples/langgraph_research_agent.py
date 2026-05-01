"""LangGraph multi-agent research workflow — parsable example.

This file is intentionally NOT runnable (it imports langgraph, which you
may not have installed). It exists so users can try::

    import semanticembed as se
    edges = se.extract.from_langgraph("examples/langgraph_research_agent.py")

The parser is pure AST — it never imports langgraph or executes any of
this code.

Topology (what `from_langgraph` will extract):

    START -> planner
    planner -> researcher
    researcher -> writer       (conditional: ready=True)
    researcher -> researcher   (conditional: ready=False, dropped as self-loop)
    writer -> critic
    critic -> writer           (conditional: needs_revision=True)
    critic -> END              (conditional: needs_revision=False)
"""

from langgraph.graph import StateGraph, START, END


def planner(state):
    """Decompose the question into research tasks."""
    return state


def researcher(state):
    """Hit web search + scratch tools."""
    return state


def writer(state):
    """Draft the answer from the research."""
    return state


def critic(state):
    """Score the draft. Either request a revision or finish."""
    return state


def research_router(state):
    return "writer" if state.get("ready") else "researcher"


def critic_router(state):
    return "writer" if state.get("needs_revision") else "END"


workflow = StateGraph(dict)
workflow.add_node("planner", planner)
workflow.add_node("researcher", researcher)
workflow.add_node("writer", writer)
workflow.add_node("critic", critic)

workflow.set_entry_point("planner")
workflow.add_edge("planner", "researcher")
workflow.add_conditional_edges(
    "researcher",
    research_router,
    {"writer": "writer", "researcher": "researcher"},
)
workflow.add_edge("writer", "critic")
workflow.add_conditional_edges(
    "critic",
    critic_router,
    {"writer": "writer", "END": END},
)

app = workflow.compile()
