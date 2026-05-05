"""SemanticEmbed — AI Agent Topology Risk Analyzer (Gradio Space).

Public demo: paste a LangGraph / CrewAI / AutoGen file or an edge list,
get the 6D structural encoding + risk findings.

Trade-secret boundary:
- This Space contains zero encoding logic. `se.encode()` POSTs the edge
  list to https://semanticembed-api-production.up.railway.app/api/v1/encode
  (the public free-tier endpoint, same as `pip install semanticembed`).
- The 6D algorithm and risk-classification thresholds run server-side
  and are not in the SDK or this Space.
- No API keys are bundled. The Space uses the unauthenticated free tier
  (50-node cap per request, enforced server-side).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import gradio as gr
import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import semanticembed as se
from semanticembed.exceptions import (
    APIError,
    NodeLimitError,
    SemanticConnectionError,
    SemanticEmbedError,
)


HERE = Path(__file__).parent
EXAMPLES_DIR = HERE / "examples"

MODE_LANGGRAPH = "LangGraph"
MODE_CREWAI = "CrewAI"
MODE_AUTOGEN = "AutoGen"
MODE_EDGES = "Edge list (JSON or CSV)"

MODE_TO_KIND = {
    MODE_LANGGRAPH: "langgraph",
    MODE_CREWAI: "crewai",
    MODE_AUTOGEN: "autogen",
    MODE_EDGES: "edges_json",
}

# Each mode has a starter file that loads into the code box on radio click.
# Users edit/replace before clicking Analyze.
STARTER_BY_MODE: dict[str, str] = {
    MODE_LANGGRAPH: "langgraph_research.py",
    MODE_CREWAI:    "crewai_content.py",
    MODE_AUTOGEN:   "autogen_codereview.py",
    MODE_EDGES:     "boutique.json",
}

# Drift tab "After" starters — each is a structurally meaningful refactor of
# the matching "Before" starter so first-click Analyze drift produces a
# non-trivial result instead of all zeros.
STARTER_AFTER_BY_MODE: dict[str, str] = {
    MODE_LANGGRAPH: "langgraph_research_after.py",
    MODE_CREWAI:    "crewai_content_after.py",
    MODE_AUTOGEN:   "autogen_codereview_after.py",
    MODE_EDGES:     "boutique_after.json",
}

PARSER_BY_KIND = {
    "langgraph": se.extract.from_langgraph,
    "crewai": se.extract.from_crewai,
    "autogen": se.extract.from_autogen,
}

LANGUAGE_BY_KIND = {
    "langgraph": "python",
    "crewai": "python",
    "autogen": "python",
    "edges_json": "json",
}


# --- Parsing -----------------------------------------------------------------


def _parse_edges_text(text: str) -> list[tuple[str, str]]:
    """Accept JSON `{"edges": [...]}` / `[[s,t],...]` / CSV / arrow-list.

    Lenient: tolerates leading whitespace, BOM, smart quotes from copy-paste,
    common arrow-list syntax (`a -> b`), and tabs / semicolons / pipes as
    delimiters. Falls back through several formats before erroring.
    """
    # Strip BOM + normalize smart quotes (common copy-paste artifact)
    text = text.lstrip("﻿").strip()
    if not text:
        raise ValueError("Empty input. Paste an edge list (JSON or CSV) or pick an example.")
    # Replace smart / typographic quotes with ASCII so json.loads works
    text = (text
            .replace("“", '"').replace("”", '"')
            .replace("‘", "'").replace("’", "'"))

    # Path 1: JSON
    if text.startswith(("{", "[")):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Looks like JSON but failed to parse: {e.msg} (line {e.lineno}, col {e.colno}). "
                "Expected `{\"edges\": [[\"a\",\"b\"], ...]}` or just `[[\"a\",\"b\"], ...]`."
            )
        edges = payload["edges"] if isinstance(payload, dict) and "edges" in payload else payload
        if not isinstance(edges, list):
            raise ValueError("JSON parsed but the top-level value isn't an edge list.")
        out: list[tuple[str, str]] = []
        for i, e in enumerate(edges):
            if isinstance(e, dict):
                s = e.get("source") or e.get("src") or e.get("from")
                t = e.get("target") or e.get("tgt") or e.get("to")
                if not s or not t:
                    raise ValueError(f"Edge {i}: dict needs `source`+`target` (or `from`+`to`).")
                out.append((str(s), str(t)))
            elif isinstance(e, (list, tuple)) and len(e) >= 2:
                out.append((str(e[0]), str(e[1])))
            else:
                raise ValueError(f"Edge {i}: expected `[source, target]`.")
        return out

    # Path 2: arrow list (`a -> b`, `a => b`, `a → b`) — common when users
    # paste from architecture docs or whiteboard photos
    arrow = re.compile(r"^\s*(\S.*?)\s*(?:->|=>|→|—>|--)\s*(\S.*?)\s*$")
    arrow_lines = [m.groups() for m in (arrow.match(ln) for ln in text.splitlines()) if m]
    if arrow_lines:
        return [(s.strip().rstrip(",;"), t.strip().rstrip(",;")) for s, t in arrow_lines]

    # Path 3: delimited (CSV / TSV / pipe / semicolon)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise ValueError("No edges in input.")
    # Pick the most-likely delimiter from the first line
    first = lines[0]
    # Skip a header row
    skip_header = first.lower().startswith(("from,", "source,", "from\t", "source\t"))
    sample = lines[1 if skip_header and len(lines) > 1 else 0]
    delim = ","
    for d in (",", "\t", "|", ";"):
        if d in sample:
            delim = d
            break
    out2: list[tuple[str, str]] = []
    for i, line in enumerate(lines[1 if skip_header else 0:], start=2 if skip_header else 1):
        cols = [c.strip() for c in line.split(delim)]
        if len(cols) < 2:
            raise ValueError(
                f"Line {i}: couldn't find two columns. "
                "Accepted formats: JSON (`{\"edges\":[[\"a\",\"b\"]]}`), "
                "CSV (`a,b`), TSV, pipe (`a|b`), or arrow list (`a -> b`)."
            )
        out2.append((cols[0], cols[1]))
    return out2


def _parse_framework_code(code: str, kind: str) -> list[tuple[str, str]]:
    """Write `code` to a temp .py and run the matching extractor."""
    parser = PARSER_BY_KIND[kind]
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp_path = f.name
    try:
        return [tuple(e) for e in parser(tmp_path)]
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _parse_input(mode: str, code: str) -> tuple[list[tuple[str, str]], str]:
    """Return (edges, kind) based on the radio mode."""
    if mode not in MODE_TO_KIND:
        raise ValueError(f"Unknown mode: {mode!r}")
    kind = MODE_TO_KIND[mode]
    if not code or not code.strip():
        raise ValueError("Code box is empty. Click a mode radio button to load a starter, or paste your own.")
    if kind == "edges_json":
        return _parse_edges_text(code), kind
    return _parse_framework_code(code, kind), kind


# --- Output rendering --------------------------------------------------------


_DIM_NAMES = ["depth", "independence", "hierarchy", "throughput", "criticality", "fanout"]


def _vec_to_dict(vec) -> dict[str, float]:
    if isinstance(vec, list):
        return {d: float(v) for d, v in zip(_DIM_NAMES, vec)}
    if isinstance(vec, dict):
        return {d: float(vec.get(d, 0.0)) for d in _DIM_NAMES}
    return {d: float(getattr(vec, d, 0.0)) for d in _DIM_NAMES}


def _summary_md(edges: list[tuple[str, str]], result, report, kind: str) -> str:
    n_nodes = result.graph_info["nodes"]
    n_edges = result.graph_info["edges"]
    max_depth = result.graph_info["max_depth"]
    n_risks = len(report.risks)
    crit_count = sum(1 for r in report.risks if r.severity == "critical")
    extracted_from = {
        "langgraph": "LangGraph workflow",
        "crewai": "CrewAI script",
        "autogen": "AutoGen script",
        "edges_json": "edge list",
    }.get(kind, "input")

    headline = (
        f"**{n_nodes} nodes · {n_edges} edges · max depth {max_depth} · "
        f"{result.encoding_time_ms:.0f}ms**"
    )
    risk_line = (
        f"{n_risks} structural risks detected"
        + (f" — **{crit_count} critical**" if crit_count else "")
        + "." if n_risks else "No structural risks detected."
    )
    return f"### Result\nExtracted from your {extracted_from}.\n\n{headline}\n\n{risk_line}"


def _df_6d(result) -> pd.DataFrame:
    rows = []
    for node, vec in result.vectors.items():
        v = _vec_to_dict(vec)
        rows.append({
            "node": node,
            "criticality": round(v["criticality"], 3),
            "throughput":  round(v["throughput"], 3),
            "depth":       round(v["depth"], 3),
            "fanout":      round(v["fanout"], 3),
            "independence": round(v["independence"], 3),
            "hierarchy":   round(v["hierarchy"], 3),
        })
    df = pd.DataFrame(rows).sort_values("criticality", ascending=False)
    return df.head(20).reset_index(drop=True)


def _risks_md(report) -> str:
    if not report.risks:
        return "*No structural risks flagged for this graph.*"
    by_sev: dict[str, list] = {"critical": [], "warning": [], "info": []}
    for r in report.risks:
        sev = r.severity if r.severity in by_sev else "info"
        by_sev[sev].append(r)

    parts: list[str] = []
    sev_emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}
    sev_label = {"critical": "Critical", "warning": "Warning", "info": "Info"}
    for sev in ("critical", "warning", "info"):
        if not by_sev[sev]:
            continue
        parts.append(f"#### {sev_emoji[sev]} {sev_label[sev]} ({len(by_sev[sev])})")
        for r in by_sev[sev]:
            desc = r.description.strip() if getattr(r, "description", "") else ""
            parts.append(f"- **{r.node}** — `{r.category}`" + (f" · {desc}" if desc else ""))
        parts.append("")
    return "\n".join(parts)


_RISK_NODE_COLOR = {
    "critical": "#dc2626",   # red-600
    "warning":  "#f59e0b",   # amber-500
    "info":     "#3b82f6",   # blue-500
}


def _choose_layout(G: nx.DiGraph) -> dict:
    """Pick a NetworkX layout that reads well for this graph's shape.

    - Sparse DAGs (≤30 nodes, edges/nodes < 1.5) → topological layered layout
      so the graph reads left-to-right by depth.
    - Small graphs (<20 nodes, has cycles) → Kamada-Kawai (compact, readable).
    - Larger / denser graphs → spring layout (current default).
    """
    n = G.number_of_nodes()
    if n == 0:
        return {}
    try:
        layers = list(nx.topological_generations(G))
    except nx.NetworkXUnfeasible:
        layers = None
    is_sparse = G.number_of_edges() < 1.5 * n
    if layers is not None and is_sparse and n <= 30:
        # Set a `layer` attribute on each node, then point multipartite_layout
        # at it. Avoids the inverted-dict shape NetworkX 3.x expects.
        for layer_idx, layer_nodes in enumerate(layers):
            for node in layer_nodes:
                G.nodes[node]["layer"] = layer_idx
        return nx.multipartite_layout(G, subset_key="layer", align="vertical")
    if n < 20:
        # kamada_kawai requires scipy; on minimal HF Space images it's not
        # always available. Fall back to spring if the import fails.
        try:
            return nx.kamada_kawai_layout(G)
        except (ImportError, ModuleNotFoundError):
            pass
    return nx.spring_layout(G, seed=42, k=1.2 / max(n ** 0.5, 1))


def _topology_plot(edges: list[tuple[str, str]], result, report) -> go.Figure:
    """Force-directed plot. Node color = criticality (gradient). Risk-flagged
    nodes get a colored ring overlay (red/amber/blue) and a callout label."""
    G = nx.DiGraph()
    G.add_edges_from(edges)
    pos = _choose_layout(G)

    # Highest-severity flag per node (critical > warning > info)
    sev_rank = {"critical": 3, "warning": 2, "info": 1}
    node_top_sev: dict[str, str] = {}
    for r in report.risks:
        cur = node_top_sev.get(r.node)
        if cur is None or sev_rank.get(r.severity, 0) > sev_rank.get(cur, 0):
            node_top_sev[r.node] = r.severity

    # Edge segments, drawn before the nodes so they sit underneath
    edge_x: list[float] = []
    edge_y: list[float] = []
    for src, tgt in G.edges():
        if src in pos and tgt in pos:
            x0, y0 = pos[src]
            x1, y1 = pos[tgt]
            edge_x += [x0, x1, None]
            edge_y += [y0, y1, None]
    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=0.8, color="#94a3b8"),  # slate-400
        hoverinfo="none",
        mode="lines",
        showlegend=False,
    )

    # Arrow annotations for direction (one per edge)
    arrows = []
    for src, tgt in G.edges():
        if src in pos and tgt in pos:
            arrows.append(dict(
                ax=pos[src][0], ay=pos[src][1],
                x=pos[tgt][0], y=pos[tgt][1],
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=2, arrowsize=1.0, arrowwidth=1,
                arrowcolor="#94a3b8",
                opacity=0.5,
            ))

    # Node markers — color encodes criticality (0 -> light, 1 -> dark red)
    nodes = list(G.nodes())
    node_x = [pos[n][0] for n in nodes]
    node_y = [pos[n][1] for n in nodes]
    crits = [_vec_to_dict(result.vectors[n])["criticality"] for n in nodes]
    fanouts = [_vec_to_dict(result.vectors[n])["fanout"] for n in nodes]
    sizes = [22 + 28 * c for c in crits]  # critical nodes are bigger
    hovers = []
    for n in nodes:
        v = _vec_to_dict(result.vectors[n])
        sev = node_top_sev.get(n)
        sev_line = f"<br><b>Risk: {sev}</b>" if sev else ""
        hovers.append(
            f"<b>{n}</b>{sev_line}<br>"
            f"depth={v['depth']:.2f} indep={v['independence']:.2f}<br>"
            f"hier={v['hierarchy']:.2f} thru={v['throughput']:.2f}<br>"
            f"<b>crit={v['criticality']:.3f}</b> fanout={v['fanout']:.2f}"
        )
    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        marker=dict(
            size=sizes,
            color=crits,
            colorscale=[[0, "#cbd5e1"], [0.5, "#fb923c"], [1, "#dc2626"]],
            cmin=0, cmax=max(max(crits) if crits else 1, 0.1),
            line=dict(width=2, color="#1e293b"),
            colorbar=dict(
                title=dict(text="Criticality", side="right"),
                thickness=12, len=0.6, x=1.02,
            ),
        ),
        text=nodes,
        textposition="bottom center",
        textfont=dict(size=10, color="#1e293b"),
        hovertext=hovers,
        hoverinfo="text",
        showlegend=False,
    )

    # Severity ring overlay for risk-flagged nodes
    rings = []
    for sev_label, color in _RISK_NODE_COLOR.items():
        nx_ring = [n for n in nodes if node_top_sev.get(n) == sev_label]
        if not nx_ring:
            continue
        rings.append(go.Scatter(
            x=[pos[n][0] for n in nx_ring],
            y=[pos[n][1] for n in nx_ring],
            mode="markers",
            marker=dict(
                size=[sizes[nodes.index(n)] + 10 for n in nx_ring],
                color="rgba(0,0,0,0)",
                line=dict(width=3, color=color),
            ),
            name=f"{sev_label} risk",
            hoverinfo="skip",
            showlegend=True,
        ))

    fig = go.Figure(data=[edge_trace] + rings + [node_trace])
    fig.update_layout(
        showlegend=bool(rings),
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.12,
            xanchor="center", x=0.5,
        ),
        annotations=arrows,
        margin=dict(l=10, r=70, t=20, b=20),
        xaxis=dict(showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False, visible=False),
        plot_bgcolor="white",
        height=520,
    )
    return fig


def _empty_plot() -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        xaxis=dict(showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False, visible=False),
        margin=dict(l=10, r=10, t=10, b=10),
        height=520,
        plot_bgcolor="white",
    )
    return fig


def _empty_state(message: str):
    """Used for both errors and the initial state."""
    empty_picker = gr.update(choices=[], value=None)
    empty_detail = "_Run **Analyze** first to load a topology, then pick a node to inspect._"
    return (
        message,
        _empty_plot(),
        pd.DataFrame(columns=["node"] + _DIM_NAMES),
        "",
        {},
        empty_picker,
        empty_detail,
    )


def _build_state(edges, result, report) -> dict:
    """Serializable snapshot of the last analyze() output for click lookups."""
    return {
        "nodes": list(result.vectors.keys()),
        "vectors": {n: _vec_to_dict(v) for n, v in result.vectors.items()},
        "risks": [
            {
                "node": r.node,
                "category": r.category,
                "severity": r.severity,
                "description": getattr(r, "description", ""),
                "value": getattr(r, "value", 0.0),
            }
            for r in report.risks
        ],
    }


def _node_detail_md(node: str, v: dict, risks: list[dict]) -> str:
    """Markdown card for a clicked node — full 6D vector + any matching risks."""
    sev_emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}
    bars = []
    for dim in _DIM_NAMES:
        val = v.get(dim, 0.0)
        bar_n = int(val * 20)
        bar = "█" * bar_n + "░" * (20 - bar_n)
        bars.append(f"`{dim:13s}` `{bar}` `{val:.3f}`")
    parts = [f"### Selected node: `{node}`", "", *bars]
    if risks:
        parts.append("")
        parts.append(f"**{len(risks)} risk{'s' if len(risks)>1 else ''} on this node:**")
        for r in risks:
            emoji = sev_emoji.get(r["severity"], "•")
            desc = (r.get("description") or "").strip()
            parts.append(f"- {emoji} `{r['category']}` ({r['severity']})" +
                         (f" — {desc}" if desc else ""))
    else:
        parts.append("")
        parts.append("_No structural risks flagged on this node._")
    return "\n".join(parts)


def _on_node_select(state: dict | None, node: str | None) -> str:
    """Dropdown handler: render the picked node's full 6D + risks panel.

    `gr.Plot` has no click event in Gradio 5.x, so node inspection runs through
    a dropdown populated from the last analyze() call (sorted by criticality
    descending).
    """
    if not state or not state.get("vectors"):
        return "_Run **Analyze** first to load a topology, then pick a node to inspect._"
    if not node:
        return "_Pick a node from the dropdown to see its full 6D + risks._"
    if node not in state["vectors"]:
        return f"_Node `{node}` is not in the current encoding._"
    matched = [r for r in state["risks"] if r["node"] == node]
    return _node_detail_md(node, state["vectors"][node], matched)


def _picker_choices(state: dict) -> list[str]:
    """Node names sorted by criticality desc — most-interesting nodes first."""
    crits = {n: state["vectors"][n].get("criticality", 0.0) for n in state["nodes"]}
    return sorted(state["nodes"], key=lambda n: crits.get(n, 0.0), reverse=True)


# --- Analyze (the click handler) ---------------------------------------------


def analyze(mode: str, code: str):
    try:
        edges, kind = _parse_input(mode, code)
    except (ValueError, json.JSONDecodeError) as e:
        return _empty_state(f"**Couldn't parse the input.**\n\n{e}")
    except SyntaxError as e:
        return _empty_state(f"**Python syntax error in the pasted code.**\n\n`{e}`")
    except Exception as e:  # parser surprise — surface the message
        return _empty_state(f"**Parser error.**\n\n`{type(e).__name__}: {e}`")

    if not edges:
        hint = {
            "langgraph": (
                "**LangGraph** parser looks for: `g.add_edge(\"x\", \"y\")`, "
                "`g.add_conditional_edges(\"x\", router, {\"a\": \"y\", ...})`, "
                "`g.set_entry_point(...)`, `g.set_finish_point(...)`. "
                "Make sure your file has explicit calls (not just `compile()` of a pre-built graph)."
            ),
            "crewai": (
                "**CrewAI** parser looks for: `Task(agent=X)` (emits agent → task), "
                "`Task(context=[t1, t2])` (task→task dependency), "
                "and `Crew(manager_agent=mgr)` (manager fan-out). "
                "Make sure agents and tasks are top-level variable assignments."
            ),
            "autogen": (
                "**AutoGen** parser supports: legacy `GroupChat([...])` + optional "
                "`GroupChatManager`, modern `RoundRobinGroupChat` / `SelectorGroupChat` / "
                "`Swarm` / `MagenticOneGroupChat`, and `x.initiate_chat(y, ...)`. "
                "If you're using a different pattern, paste your edges directly via "
                "the **Edge list** mode."
            ),
            "edges_json": (
                "Couldn't find any edges. Accepted formats: JSON (`{\"edges\":[[\"a\",\"b\"], ...]}`), "
                "CSV (`a,b` per line), TSV, pipe-separated, or arrow list (`a -> b`)."
            ),
        }.get(kind, "Couldn't extract edges from the input.")
        return _empty_state(
            f"**No edges extracted.** {hint}\n\n"
            "Tip: switch to the **Edge list** mode and paste an explicit edge list "
            "if your framework file uses a pattern we don't recognize yet."
        )
    if len(edges) < 2:
        return _empty_state(
            "Need at least 2 edges for a meaningful encoding. "
            f"Found {len(edges)}."
        )

    try:
        result = se.encode(edges)
        report = se.report(result)
    except NodeLimitError as e:
        return _empty_state(
            f"**Free tier limit reached.** Your graph has {e.n_nodes} nodes; "
            f"the free tier covers up to {e.limit}.\n\n"
            "Email [jeffmurr@seas.upenn.edu](mailto:jeffmurr@seas.upenn.edu) "
            "for a license key, or trim the graph to fit."
        )
    except SemanticConnectionError as e:
        return _empty_state(
            f"**Couldn't reach the SemanticEmbed API.** {e}\n\n"
            "If this persists, the encoding service may be cold-starting; "
            "try again in 30 seconds."
        )
    except APIError as e:
        return _empty_state(f"**Server returned an error.** Status {e.status}: `{e.detail}`")
    except SemanticEmbedError as e:
        return _empty_state(f"**Encoding error.** `{type(e).__name__}: {e}`")

    # Surface any rendering bugs in the summary instead of letting Gradio
    # swallow them with a generic "Error" badge.
    try:
        state = _build_state(edges, result, report)
        choices = _picker_choices(state)
        # Auto-select the highest-criticality node so users see a populated
        # detail panel immediately — no extra click required.
        first_node = choices[0] if choices else None
        first_detail = (
            _on_node_select(state, first_node) if first_node
            else "_No nodes to inspect._"
        )
        return (
            _summary_md(edges, result, report, kind),
            _topology_plot(edges, result, report),
            _df_6d(result),
            _risks_md(report),
            state,
            gr.update(choices=choices, value=first_node),
            first_detail,
        )
    except Exception as e:
        import traceback
        return _empty_state(
            f"**Render error.** `{type(e).__name__}: {e}`\n\n"
            f"```\n{traceback.format_exc()[-1500:]}\n```"
        )


# --- Drift comparison (Phase C) ---------------------------------------------


def _crit(result, node: str) -> float:
    """Criticality of `node` in `result`, or 0 if missing."""
    if node not in result.vectors:
        return 0.0
    return _vec_to_dict(result.vectors[node])["criticality"]


def _drift_summary_md(
    edges_a, edges_b, result_a, result_b, threshold: float = 0.05
) -> str:
    """Headline: X added · Y removed · Z changed criticality by >threshold."""
    nodes_a = set(result_a.vectors.keys())
    nodes_b = set(result_b.vectors.keys())
    added = nodes_b - nodes_a
    removed = nodes_a - nodes_b
    common = nodes_a & nodes_b
    changed = sum(
        1 for n in common
        if abs(_crit(result_b, n) - _crit(result_a, n)) > threshold
    )
    n_a = len(nodes_a)
    n_b = len(nodes_b)
    e_a = len(edges_a)
    e_b = len(edges_b)
    return (
        f"### Drift summary\n"
        f"**Before:** {n_a} nodes · {e_a} edges  →  "
        f"**After:** {n_b} nodes · {e_b} edges\n\n"
        f"**{len(added)} added** · **{len(removed)} removed** · "
        f"**{changed} changed criticality by > {threshold:.2f}**"
    )


def _drift_plot(edges_a, edges_b, result_a, result_b) -> go.Figure:
    """Union graph with edge-level diff coloring.

    - Edges in BOTH: thin gray solid (unchanged).
    - Edges in AFTER only: teal solid (added).
    - Edges in BEFORE only: gray dashed (removed).
    Same color language as the node markers (teal=added, gray=removed).
    """
    G = nx.DiGraph()
    G.add_edges_from(list(edges_a) + list(edges_b))
    pos = _choose_layout(G)

    nodes_a = set(result_a.vectors.keys())
    nodes_b = set(result_b.vectors.keys())

    edges_a_set = {(s, t) for s, t in edges_a}
    edges_b_set = {(s, t) for s, t in edges_b}
    common_edges = edges_a_set & edges_b_set
    added_edges = edges_b_set - edges_a_set
    removed_edges = edges_a_set - edges_b_set

    def _segments(edge_set):
        xs: list[float] = []
        ys: list[float] = []
        for src, tgt in edge_set:
            if src in pos and tgt in pos:
                x0, y0 = pos[src]
                x1, y1 = pos[tgt]
                xs += [x0, x1, None]
                ys += [y0, y1, None]
        return xs, ys

    cx, cy = _segments(common_edges)
    ax_, ay_ = _segments(added_edges)
    rx, ry = _segments(removed_edges)

    edge_traces = []
    edge_traces.append(go.Scatter(
        x=cx, y=cy,
        line=dict(width=0.8, color="#94a3b8"),
        hoverinfo="none", mode="lines",
        name="edge: in both", showlegend=bool(common_edges),
    ))
    edge_traces.append(go.Scatter(
        x=ax_, y=ay_,
        line=dict(width=2.4, color="#0d9488"),  # teal-600 = added
        hoverinfo="none", mode="lines",
        name="edge: added", showlegend=bool(added_edges),
    ))
    edge_traces.append(go.Scatter(
        x=rx, y=ry,
        line=dict(width=2.0, color="#94a3b8", dash="dash"),
        hoverinfo="none", mode="lines",
        name="edge: removed", showlegend=bool(removed_edges),
    ))

    # Categorize nodes
    added_nodes = [n for n in G.nodes() if n in nodes_b and n not in nodes_a]
    removed_nodes = [n for n in G.nodes() if n in nodes_a and n not in nodes_b]
    common_nodes = [n for n in G.nodes() if n in nodes_a and n in nodes_b]

    deltas = [_crit(result_b, n) - _crit(result_a, n) for n in common_nodes]
    abs_max = max([abs(d) for d in deltas] + [0.05])  # avoid 0 range

    # Common: diverging red/green, size by max(crit_a, crit_b)
    common_x = [pos[n][0] for n in common_nodes]
    common_y = [pos[n][1] for n in common_nodes]
    common_sizes = [
        22 + 28 * max(_crit(result_a, n), _crit(result_b, n))
        for n in common_nodes
    ]
    common_hover = []
    for n in common_nodes:
        ca = _crit(result_a, n)
        cb = _crit(result_b, n)
        common_hover.append(
            f"<b>{n}</b><br>"
            f"crit before: {ca:.3f}<br>"
            f"crit after:  {cb:.3f}<br>"
            f"<b>Δ crit:    {cb - ca:+.3f}</b>"
        )
    common_trace = go.Scatter(
        x=common_x, y=common_y,
        mode="markers+text",
        marker=dict(
            size=common_sizes,
            color=deltas,
            colorscale=[[0, "#16a34a"], [0.5, "#cbd5e1"], [1, "#dc2626"]],
            cmin=-abs_max, cmax=abs_max,
            line=dict(width=2, color="#1e293b"),
            colorbar=dict(
                title=dict(text="Δ criticality<br>(red=worse)", side="right"),
                thickness=12, len=0.6, x=1.02,
            ),
        ),
        text=common_nodes,
        textposition="bottom center",
        textfont=dict(size=10, color="#1e293b"),
        hovertext=common_hover,
        hoverinfo="text",
        name="in both",
        showlegend=True,
    )

    # Added: teal markers with bold ring
    added_trace = go.Scatter(
        x=[pos[n][0] for n in added_nodes],
        y=[pos[n][1] for n in added_nodes],
        mode="markers+text",
        marker=dict(
            size=[22 + 28 * _crit(result_b, n) for n in added_nodes],
            color="#0d9488",  # teal-600
            line=dict(width=3, color="#0f766e"),
        ),
        text=[f"+ {n}" for n in added_nodes],
        textposition="bottom center",
        textfont=dict(size=10, color="#0f766e"),
        hovertext=[
            f"<b>{n}</b><br><b>ADDED</b><br>crit after: {_crit(result_b, n):.3f}"
            for n in added_nodes
        ],
        hoverinfo="text",
        name="added",
        showlegend=bool(added_nodes),
    )

    # Removed: faded gray markers
    removed_trace = go.Scatter(
        x=[pos[n][0] for n in removed_nodes],
        y=[pos[n][1] for n in removed_nodes],
        mode="markers+text",
        marker=dict(
            size=[22 + 28 * _crit(result_a, n) for n in removed_nodes],
            color="#cbd5e1",  # slate-300
            line=dict(width=2, color="#64748b", dash="dot"),
            symbol="x",
        ),
        text=[f"− {n}" for n in removed_nodes],
        textposition="bottom center",
        textfont=dict(size=10, color="#475569"),
        hovertext=[
            f"<b>{n}</b><br><b>REMOVED</b><br>crit before: {_crit(result_a, n):.3f}"
            for n in removed_nodes
        ],
        hoverinfo="text",
        name="removed",
        showlegend=bool(removed_nodes),
    )

    # Direction arrows colored by edge category
    arrows = []
    for src, tgt in common_edges:
        if src in pos and tgt in pos:
            arrows.append(dict(
                ax=pos[src][0], ay=pos[src][1],
                x=pos[tgt][0],  y=pos[tgt][1],
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=2, arrowsize=1.0, arrowwidth=1,
                arrowcolor="#94a3b8", opacity=0.5,
            ))
    for src, tgt in added_edges:
        if src in pos and tgt in pos:
            arrows.append(dict(
                ax=pos[src][0], ay=pos[src][1],
                x=pos[tgt][0],  y=pos[tgt][1],
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=2, arrowsize=1.2, arrowwidth=1.5,
                arrowcolor="#0d9488", opacity=0.85,
            ))
    for src, tgt in removed_edges:
        if src in pos and tgt in pos:
            arrows.append(dict(
                ax=pos[src][0], ay=pos[src][1],
                x=pos[tgt][0],  y=pos[tgt][1],
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=2, arrowsize=1.0, arrowwidth=1,
                arrowcolor="#94a3b8", opacity=0.45,
            ))

    fig = go.Figure(data=edge_traces + [common_trace, added_trace, removed_trace])
    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.18,
            xanchor="center", x=0.5,
        ),
        annotations=arrows,
        margin=dict(l=10, r=70, t=20, b=40),
        xaxis=dict(showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False, visible=False),
        plot_bgcolor="white",
        height=560,
    )
    return fig


def _drift_table(result_a, result_b) -> pd.DataFrame:
    """One row per node in the union, sorted by |Δ criticality| desc, top 20."""
    nodes = list(set(result_a.vectors) | set(result_b.vectors))
    rows = []
    for n in nodes:
        va = _vec_to_dict(result_a.vectors[n]) if n in result_a.vectors else None
        vb = _vec_to_dict(result_b.vectors[n]) if n in result_b.vectors else None
        ca = va["criticality"] if va else None
        cb = vb["criticality"] if vb else None
        ta = va["throughput"] if va else None
        tb = vb["throughput"] if vb else None
        fa = va["fanout"] if va else None
        fb = vb["fanout"] if vb else None
        # Δ values are 0 if either side missing (the status column captures it)
        d_crit = (cb or 0.0) - (ca or 0.0)
        d_thru = (tb or 0.0) - (ta or 0.0)
        d_fan = (fb or 0.0) - (fa or 0.0)
        if va is None:
            status = "+ added"
        elif vb is None:
            status = "− removed"
        else:
            status = "in both"
        rows.append({
            "node": n,
            "status": status,
            "before crit": round(ca, 3) if ca is not None else None,
            "after crit":  round(cb, 3) if cb is not None else None,
            "Δ crit":      round(d_crit, 3),
            "Δ throughput": round(d_thru, 3),
            "Δ fanout":    round(d_fan, 3),
        })
    df = pd.DataFrame(rows)
    df["__abs"] = df["Δ crit"].abs()
    df = df.sort_values("__abs", ascending=False).drop(columns="__abs").head(20)
    return df.reset_index(drop=True)


def _empty_drift() -> tuple[str, go.Figure, pd.DataFrame]:
    return (
        "_Paste your **before** and **after** code, then click Analyze drift._",
        _empty_plot(),
        pd.DataFrame(columns=["node", "status", "before crit", "after crit",
                              "Δ crit", "Δ throughput", "Δ fanout"]),
    )


def analyze_drift(mode: str, code_a: str, code_b: str):
    """Encode both graphs (same mode), return summary + union plot + diff table."""
    try:
        edges_a, _ = _parse_input(mode, code_a)
        edges_b, _ = _parse_input(mode, code_b)
    except (ValueError, json.JSONDecodeError) as e:
        return ("**Couldn't parse the input.**\n\n" + str(e),
                _empty_plot(), _empty_drift()[2])
    except SyntaxError as e:
        return f"**Python syntax error.** `{e}`", _empty_plot(), _empty_drift()[2]
    except Exception as e:
        return (f"**Parser error.** `{type(e).__name__}: {e}`",
                _empty_plot(), _empty_drift()[2])

    if len(edges_a) < 2 or len(edges_b) < 2:
        return ("Both inputs need at least 2 edges. "
                f"Got {len(edges_a)} (before) and {len(edges_b)} (after).",
                _empty_plot(), _empty_drift()[2])

    try:
        # The cache makes a second click free if either side hasn't changed.
        result_a = se.encode(edges_a, cache=True)
        result_b = se.encode(edges_b, cache=True)
    except NodeLimitError as e:
        return (f"**Free tier limit reached.** {e.n_nodes} nodes, "
                f"limit {e.limit}.", _empty_plot(), _empty_drift()[2])
    except SemanticConnectionError as e:
        return (f"**Couldn't reach the API.** {e}",
                _empty_plot(), _empty_drift()[2])
    except APIError as e:
        return (f"**Server error {e.status}:** `{e.detail}`",
                _empty_plot(), _empty_drift()[2])
    except SemanticEmbedError as e:
        return (f"**Encoding error.** `{type(e).__name__}: {e}`",
                _empty_plot(), _empty_drift()[2])

    try:
        return (
            _drift_summary_md(edges_a, edges_b, result_a, result_b),
            _drift_plot(edges_a, edges_b, result_a, result_b),
            _drift_table(result_a, result_b),
        )
    except Exception as e:
        import traceback
        return (f"**Render error.** `{type(e).__name__}: {e}`\n\n"
                f"```\n{traceback.format_exc()[-1500:]}\n```",
                _empty_plot(), _empty_drift()[2])


# --- UI ----------------------------------------------------------------------

INTRO_MD = """\
# 🕸️ SemanticEmbed — AI Agent Topology Risk Analyzer

**Pick a mode → click Analyze.** Get a **6D structural encoding** plus
risk findings — single points of failure, amplification cascades,
convergence sinks — from topology alone.

Each mode loads a starter example into the code box. Edit it, paste
your own file over it, or just hit Analyze on the example to see what
the output looks like.

Designed for AI agent pipelines where vendor concentration, gateway
bottlenecks, and guardrail SPOFs hide in the orchestration graph.

[PyPI](https://pypi.org/project/semanticembed/) ·
[GitHub](https://github.com/jmurray10/semanticembed-sdk) ·
[Demo dashboard](https://semanticembed-dashboard.vercel.app/) ·
[Validation methodology](https://github.com/jmurray10/semanticembed-sdk/blob/main/docs/validation_methodology.md)

> Encoding runs server-side. The Space sends only the edge list — your
> file content stays on this machine.
"""

CSS = """
#summary { min-height: 80px; }
.gradio-container { max-width: 1100px !important; }
"""


def _starter_for(mode: str) -> str:
    """Read the 'before' starter file bundled for `mode`."""
    fname = STARTER_BY_MODE.get(mode)
    if not fname:
        return ""
    return (EXAMPLES_DIR / fname).read_text(encoding="utf-8")


def _starter_after_for(mode: str) -> str:
    """Read the 'after' starter file (drift tab right-hand box)."""
    fname = STARTER_AFTER_BY_MODE.get(mode)
    if not fname:
        return ""
    return (EXAMPLES_DIR / fname).read_text(encoding="utf-8")


def _on_mode_change(mode: str) -> tuple:
    """Click a radio → switch editor language AND auto-load matching starter.

    User flow: click radio → see code → click Analyze. Two clicks, done.
    If the user wants their own code, they paste over the starter before
    clicking Analyze.
    """
    kind = MODE_TO_KIND.get(mode, "edges_json")
    lang = LANGUAGE_BY_KIND[kind]
    starter = _starter_for(mode)
    return gr.update(language=lang, value=starter)


with gr.Blocks(title="SemanticEmbed — AI Agent Topology Risk", css=CSS) as demo:
    gr.Markdown(INTRO_MD)

    with gr.Tabs():
        with gr.Tab("Single graph"):
            mode = gr.Radio(
                choices=[MODE_LANGGRAPH, MODE_CREWAI, MODE_AUTOGEN, MODE_EDGES],
                value=MODE_LANGGRAPH,
                label="Mode",
                info=(
                    "Pick what kind of input you have. The matching example loads "
                    "into the code box below — paste your own code over it, or leave "
                    "the example and click Analyze."
                ),
            )

            code_box = gr.Code(
                label="Source / edge list",
                language="python",
                lines=14,
                value="",
            )

            analyze_btn = gr.Button("Analyze", variant="primary", size="lg")

            summary_md = gr.Markdown(elem_id="summary")

            gr.Markdown(
                "### Topology graph\n"
                "_Node size and color encode criticality (bigger and redder = more "
                "structural risk). Risk-flagged nodes get a colored ring. Hover for "
                "the full 6D vector. Use the **Inspect node** picker below for the "
                "full breakdown of any node._"
            )
            plot_out = gr.Plot(label="", show_label=False)

            node_picker = gr.Dropdown(
                choices=[], value=None, label="Inspect node",
                info="Pick a node to see its full 6D vector and any risks. Sorted by criticality.",
                interactive=True, allow_custom_value=False,
            )
            selected_md = gr.Markdown(
                "_Run **Analyze** first to load a topology, then pick a node to inspect._"
            )

            gr.Markdown("### 6D structural encoding (top 20 nodes by criticality)")
            table_out = gr.Dataframe(interactive=False, wrap=True)
            gr.Markdown("### Structural risks")
            risks_md = gr.Markdown()

            # In-process snapshot of the last analyze() output. The node-picker
            # change handler reads from this to render the selected node's detail.
            analyze_state = gr.State(value={})

        with gr.Tab("Compare two graphs"):
            gr.Markdown(
                "### Drift comparison\n"
                "Paste your **before** code on the left and the **after** version "
                "on the right (same mode for both). The union graph shows nodes "
                "added (teal +), removed (gray ×), and Δ criticality for nodes "
                "in both. Useful for architecture review: _what did this refactor "
                "actually change about structural risk?_"
            )

            drift_mode = gr.Radio(
                choices=[MODE_LANGGRAPH, MODE_CREWAI, MODE_AUTOGEN, MODE_EDGES],
                value=MODE_LANGGRAPH,
                label="Mode (applies to both sides)",
            )

            with gr.Row():
                drift_code_a = gr.Code(
                    label="Before",
                    language="python",
                    lines=14,
                    value="",
                )
                drift_code_b = gr.Code(
                    label="After",
                    language="python",
                    lines=14,
                    value="",
                )

            drift_btn = gr.Button("Analyze drift", variant="primary", size="lg")
            drift_summary_md = gr.Markdown()
            drift_plot_out = gr.Plot(label="", show_label=False)
            gr.Markdown("### Per-node delta (top 20 by |Δ criticality|)")
            drift_table_out = gr.Dataframe(interactive=False, wrap=True)

    # --- Event wiring: Single-graph tab ---
    mode.change(fn=_on_mode_change, inputs=mode, outputs=code_box)
    analyze_btn.click(
        fn=analyze, inputs=[mode, code_box],
        outputs=[summary_md, plot_out, table_out, risks_md,
                 analyze_state, node_picker, selected_md],
    )
    node_picker.change(
        fn=_on_node_select,
        inputs=[analyze_state, node_picker],
        outputs=selected_md,
    )

    # --- Event wiring: Drift tab ---
    def _on_drift_mode_change(m: str) -> tuple:
        lang = LANGUAGE_BY_KIND[MODE_TO_KIND[m]]
        return (
            gr.update(language=lang, value=_starter_for(m)),
            gr.update(language=lang, value=_starter_after_for(m)),
        )

    drift_mode.change(
        fn=_on_drift_mode_change,
        inputs=drift_mode,
        outputs=[drift_code_a, drift_code_b],
    )
    drift_btn.click(
        fn=analyze_drift,
        inputs=[drift_mode, drift_code_a, drift_code_b],
        outputs=[drift_summary_md, drift_plot_out, drift_table_out],
    )

    # Prefill all three code boxes. Drift's "After" loads the *_after.* file
    # so the very first Analyze drift produces a non-trivial result.
    demo.load(fn=lambda: _starter_for(MODE_LANGGRAPH), inputs=None, outputs=code_box)
    demo.load(fn=lambda: _starter_for(MODE_LANGGRAPH),       inputs=None, outputs=drift_code_a)
    demo.load(fn=lambda: _starter_after_for(MODE_LANGGRAPH), inputs=None, outputs=drift_code_b)

    gr.Markdown("""
---
**Built by [Jeff Murray](https://www.linkedin.com/in/jeff-murray-ai)** ·
[GitHub @jmurray10](https://github.com/jmurray10) ·
Patent pending · Application #63/994,075
""")


if __name__ == "__main__":
    demo.launch()
