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
import pandas as pd
import semanticembed as se
from semanticembed.exceptions import (
    APIError,
    NodeLimitError,
    SemanticConnectionError,
    SemanticEmbedError,
)


HERE = Path(__file__).parent
EXAMPLES_DIR = HERE / "examples"

# (label, kind, filename) — kind picks the parser at analyze time.
EXAMPLES: list[tuple[str, str, str]] = [
    ("LangGraph: research workflow (6 edges)", "langgraph", "langgraph_research.py"),
    ("CrewAI: content pipeline (11 edges)",    "crewai",    "crewai_content.py"),
    ("AutoGen: code review group chat (5 edges)", "autogen", "autogen_codereview.py"),
    ("Edge list: Google Online Boutique (15 edges)", "edges_json", "boutique.json"),
]
EXAMPLE_LABELS = [label for label, _, _ in EXAMPLES]
EXAMPLE_BY_LABEL = {label: (kind, fname) for label, kind, fname in EXAMPLES}


MODE_LANGGRAPH = "LangGraph"
MODE_CREWAI = "CrewAI"
MODE_AUTOGEN = "AutoGen"
MODE_EDGES = "Edge list (JSON or CSV)"
MODE_EXAMPLE = "Try an example"

MODE_TO_KIND = {
    MODE_LANGGRAPH: "langgraph",
    MODE_CREWAI: "crewai",
    MODE_AUTOGEN: "autogen",
    MODE_EDGES: "edges_json",
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


def _parse_input(mode: str, code: str, example_label: str) -> tuple[list[tuple[str, str]], str]:
    """Return (edges, kind) based on the radio mode."""
    if mode == MODE_EXAMPLE:
        if not example_label or example_label not in EXAMPLE_BY_LABEL:
            raise ValueError("Pick an example from the dropdown.")
        kind, fname = EXAMPLE_BY_LABEL[example_label]
        loaded = (EXAMPLES_DIR / fname).read_text(encoding="utf-8")
        if kind == "edges_json":
            return _parse_edges_text(loaded), kind
        return _parse_framework_code(loaded, kind), kind

    if mode not in MODE_TO_KIND:
        raise ValueError(f"Unknown mode: {mode!r}")
    kind = MODE_TO_KIND[mode]
    if not code or not code.strip():
        raise ValueError("Paste a file or edge list, or pick an example.")
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


def _empty_state(message: str) -> tuple[str, pd.DataFrame, str]:
    """Used for both errors and the initial state."""
    return message, pd.DataFrame(columns=["node"] + _DIM_NAMES), ""


# --- Analyze (the click handler) ---------------------------------------------


def analyze(mode: str, code: str, example_label: str):
    try:
        edges, kind = _parse_input(mode, code, example_label)
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

    return _summary_md(edges, result, report, kind), _df_6d(result), _risks_md(report)


# --- UI ----------------------------------------------------------------------

INTRO_MD = """\
# 🕸️ SemanticEmbed — AI Agent Topology Risk Analyzer

Paste a **LangGraph**, **CrewAI**, or **AutoGen** Python file (or any
directed-graph edge list) and get a **6D structural encoding** plus
risk findings — single points of failure, amplification cascades,
convergence sinks — from topology alone.

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


def _example_choice_change(mode: str, label: str) -> str:
    """When the user picks an example, prefill the code box with its content."""
    if mode != MODE_EXAMPLE or not label or label not in EXAMPLE_BY_LABEL:
        return gr.update()
    _, fname = EXAMPLE_BY_LABEL[label]
    text = (EXAMPLES_DIR / fname).read_text(encoding="utf-8")
    return text


def _mode_change(mode: str, current_code: str) -> tuple:
    """Switch the code editor's language and example dropdown visibility based on mode."""
    if mode == MODE_EXAMPLE:
        return (
            gr.update(visible=True),
            gr.update(language="python", interactive=True),
        )
    kind = MODE_TO_KIND.get(mode, "edges_json")
    lang = LANGUAGE_BY_KIND[kind]
    return (
        gr.update(visible=False, value=None),
        gr.update(language=lang),
    )


with gr.Blocks(title="SemanticEmbed — AI Agent Topology Risk", css=CSS) as demo:
    gr.Markdown(INTRO_MD)

    with gr.Row():
        mode = gr.Radio(
            choices=[MODE_LANGGRAPH, MODE_CREWAI, MODE_AUTOGEN, MODE_EDGES, MODE_EXAMPLE],
            value=MODE_EXAMPLE,
            label="Mode",
            info="Pick what you have. Source files are parsed via AST locally — only the extracted edge list is sent to the encoding API.",
        )

    example_dd = gr.Dropdown(
        choices=EXAMPLE_LABELS,
        value=EXAMPLE_LABELS[0],
        label="Example",
        visible=True,
    )

    code_box = gr.Code(
        label="Source / edge list",
        language="python",
        lines=14,
        value="",
    )

    analyze_btn = gr.Button("Analyze", variant="primary", size="lg")

    summary_md = gr.Markdown(elem_id="summary")
    gr.Markdown("### 6D structural encoding (top 20 nodes by criticality)")
    table_out = gr.Dataframe(interactive=False, wrap=True)
    gr.Markdown("### Structural risks")
    risks_md = gr.Markdown()

    # Event wiring
    mode.change(fn=_mode_change, inputs=[mode, code_box], outputs=[example_dd, code_box])
    example_dd.change(fn=_example_choice_change, inputs=[mode, example_dd], outputs=code_box)
    analyze_btn.click(fn=analyze, inputs=[mode, code_box, example_dd],
                      outputs=[summary_md, table_out, risks_md])

    # Prefill the code box with the first example on load.
    demo.load(fn=lambda: _example_choice_change(MODE_EXAMPLE, EXAMPLE_LABELS[0]),
              inputs=None, outputs=code_box)

    gr.Markdown("""
---
**Built by [Jeff Murray](https://www.linkedin.com/in/jeff-murray-ai)** ·
[GitHub @jmurray10](https://github.com/jmurray10) ·
Patent pending · Application #63/994,075
""")


if __name__ == "__main__":
    demo.launch()
