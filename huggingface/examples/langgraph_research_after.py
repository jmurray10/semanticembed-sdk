"""LangGraph multi-agent research workflow — AFTER refactor.

Same as langgraph_research.py, but with a `safety_filter` node inserted
between writer and critic. This is a typical "we added a guardrail to
the pipeline" change.

Drift you should see:

  + safety_filter   (added node)
  - writer -> critic   (removed edge — replaced by the new path)
  + writer -> safety_filter   (added edge)
  + safety_filter -> critic   (added edge)
"""

from langgraph.graph import StateGraph, START, END


def planner(state):
    return state


def researcher(state):
    return state


def writer(state):
    return state


def safety_filter(state):
    """Block unsafe outputs before they reach the critic."""
    return state


def critic(state):
    return state


def research_router(state):
    return "writer" if state.get("ready") else "researcher"


def critic_router(state):
    return "writer" if state.get("needs_revision") else "END"


workflow = StateGraph(dict)
workflow.add_node("planner", planner)
workflow.add_node("researcher", researcher)
workflow.add_node("writer", writer)
workflow.add_node("safety_filter", safety_filter)
workflow.add_node("critic", critic)

workflow.set_entry_point("planner")
workflow.add_edge("planner", "researcher")
workflow.add_conditional_edges(
    "researcher",
    research_router,
    {"writer": "writer", "researcher": "researcher"},
)
workflow.add_edge("writer", "safety_filter")
workflow.add_edge("safety_filter", "critic")
workflow.add_conditional_edges(
    "critic",
    critic_router,
    {"writer": "writer", "END": END},
)

app = workflow.compile()
