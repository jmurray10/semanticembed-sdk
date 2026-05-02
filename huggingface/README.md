---
title: AI Agent Topology Risk Analyzer
emoji: 🕸️
colorFrom: indigo
colorTo: purple
sdk: gradio
sdk_version: 5.49.1
python_version: "3.12"
app_file: app.py
pinned: false
license: other
license_name: SemanticEmbed Proprietary
license_link: https://github.com/jmurray10/semanticembed-sdk/blob/main/LICENSE
short_description: 6D structural risk for AI agent pipelines
tags:
  - agent
  - langgraph
  - crewai
  - autogen
  - topology
  - graph-analysis
  - risk-analysis
  - observability
---

# SemanticEmbed — AI Agent Topology Risk Analyzer

A live demo of [`semanticembed`](https://pypi.org/project/semanticembed/),
focused on the AI agent use case: paste a **LangGraph**, **CrewAI**, or
**AutoGen** Python file (or any directed-graph edge list) and get a
**6D structural encoding** plus risk findings — single points of failure,
amplification cascades, convergence sinks — from topology alone.

## Why "structural" risk?

Observability tells you what broke. SemanticEmbed tells you what *will*
break, from the call graph alone:

- **Vendor concentration** — every agent calls the same LLM provider; that node sits on 89% of paths.
- **Gateway bottleneck** — the routing layer between agents and models has zero lateral redundancy.
- **Guardrail SPOF** — the moderation step is the single point all decisions converge through.

These are structural patterns. They show up identically in microservice
graphs, AI agent pipelines, and CI/CD workflows. The 6D encoding makes
them computable.

## How it works

1. You paste a file or edge list.
2. The Space parses it locally (AST for framework code, JSON/CSV for edges).
3. The **edge list only** — node names, no file content — goes to the
   SemanticEmbed cloud API.
4. The API runs the 6D encoding (proprietary, server-side) and returns
   per-node vectors plus a structural risk report.
5. The Space renders the result.

The Space contains no encoding logic. The 6D algorithm is patent-pending
([Application #63/994,075](https://github.com/jmurray10/semanticembed-sdk/blob/main/LICENSE-FAQ.md#patent))
and runs server-side only.

## Try the SDK locally

```bash
pip install 'semanticembed[extract]'
```

```python
import semanticembed as se
edges = se.extract.from_langgraph("workflow.py")
result = se.encode(edges)
print(result.table)
print(se.report(result))
```

## Validation evidence

In a blind test against a live production Dynatrace environment
(108 services, 569 topology-relevant incidents over 30 days), **79.6%**
of incidents (453/569) occurred on nodes that 6D structural analysis
had flagged as risky — from the call graph alone, before any incident
occurred.

Full methodology: [docs/validation_methodology.md](https://github.com/jmurray10/semanticembed-sdk/blob/main/docs/validation_methodology.md)

## Links

- [PyPI: `semanticembed`](https://pypi.org/project/semanticembed/)
- [GitHub: `jmurray10/semanticembed-sdk`](https://github.com/jmurray10/semanticembed-sdk)
- [Demo dashboard (auth required)](https://semanticembed-dashboard.vercel.app/)
- [Validation methodology](https://github.com/jmurray10/semanticembed-sdk/blob/main/docs/validation_methodology.md)
- [License FAQ](https://github.com/jmurray10/semanticembed-sdk/blob/main/LICENSE-FAQ.md)

---

**Built by [Jeff Murray](https://www.linkedin.com/in/jeff-murray-ai)**.
Free tier covers graphs up to 50 nodes per request — no signup, no API key.
For larger graphs, email **jeffmurr@seas.upenn.edu**.
