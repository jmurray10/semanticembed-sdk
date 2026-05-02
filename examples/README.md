# Example Graphs

This directory contains ready-to-encode topologies in two formats:

## JSON edge lists

Loadable directly with `se.encode_file(path)`:

| File | What it is | Nodes | Edges |
|------|------------|-------|-------|
| [`google_online_boutique.json`](google_online_boutique.json) | Google's reference microservice demo | 11 | 15 |
| [`weaveworks_sock_shop.json`](weaveworks_sock_shop.json) | Weaveworks Sock Shop | 14 | 15 |
| [`ai_agent_pipeline.json`](ai_agent_pipeline.json) | Multi-agent LLM orchestration | 12 | 15 |
| [`cicd_pipeline.json`](cicd_pipeline.json) | CI/CD build pipeline | 12 | 17 |
| [`sample_pipeline.json`](sample_pipeline.json) | Minimal 7-node starter | 7 | 8 |

```python
import semanticembed as se
result = se.encode_file("examples/google_online_boutique.json")
print(result.table)
print(se.report(result))
```

## AI-framework Python fixtures

These files import their respective frameworks at the top, but the SDK
parses them via AST and **never executes or imports the framework**. So
you can run the parser without `pip install langgraph`.

| File | Extractor | Edges |
|------|-----------|-------|
| [`langgraph_research_agent.py`](langgraph_research_agent.py) | `extract.from_langgraph` | 6 |
| [`crewai_content_pipeline.py`](crewai_content_pipeline.py) | `extract.from_crewai` | 11 |
| [`autogen_codereview.py`](autogen_codereview.py) | `extract.from_autogen` | 5 |

```python
import semanticembed as se
edges = se.extract.from_langgraph("examples/langgraph_research_agent.py")
result = se.encode(edges)
print(result.table)
```

## React components

The [`react/`](react/) subdirectory has drop-in React components that
render SDK output (table, radar chart, risk list). See `react/README.md`
or the relevant section in the top-level [README](../README.md).

## Schema

JSON edge lists use the same schema across all files:

```json
{
  "name": "...",
  "description": "...",
  "edges": [
    {"source": "node_a", "target": "node_b"}
  ]
}
```

Tuple / list / dict edge formats are all accepted by `encode()`. See
[`docs/input_format.md`](../docs/input_format.md).
