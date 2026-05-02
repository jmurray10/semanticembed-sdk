# SemanticEmbed Agent

An LLM-powered structural analysis assistant built on the Claude Agent SDK.

The agent autonomously scans your codebase, extracts service dependencies, runs 6D structural encoding, and explains the results in plain language. Ask follow-up questions, simulate architecture changes, and get actionable recommendations.

## How It Works

```
Your Code  ──→  Agent scans for infra files (docker-compose, k8s, terraform, Python imports)
                    │
                    ▼
              Extracts edges automatically
                    │
                    ▼
              Encodes via SemanticEmbed API (deterministic, server-side)
                    │
                    ▼
              LLM interprets results (your Anthropic key)
                    │
                    ▼
              Plain language analysis + actionable recommendations
```

The 6D encoding is deterministic and proprietary (runs server-side). The LLM only sees the output vectors and risk report — never the algorithm.

## Install

Two agent options — pick your LLM provider:

### Claude Agent (Anthropic)

```bash
pip install semanticembed claude-agent-sdk pyyaml
export ANTHROPIC_API_KEY=sk-ant-...
```

### Gemini Agent (Google)

```bash
pip install semanticembed google-genai pyyaml
export GOOGLE_API_KEY=...
```

## Usage

### Claude Agent

```bash
# Interactive — scans your project, explains risks, answers questions
semanticembed-agent

# Analyze a specific project
semanticembed-agent /path/to/project

# Single question
semanticembed-agent --ask "What is my biggest single point of failure?"
```

### Gemini Agent

```bash
# Interactive
semanticembed-gemini-agent

# Analyze a specific project
semanticembed-gemini-agent /path/to/project

# Single question
semanticembed-gemini-agent --ask "What happens if the database goes down?"

# Use a different Gemini model
semanticembed-gemini-agent --model gemini-2.5-pro
```

Both agents have the same 7 tools and produce equivalent results — just different LLM backends.

The agent will:
1. Scan for infrastructure files
2. Extract edges
3. Encode the graph
4. Present a structural risk summary
5. Wait for your questions

## What the Agent Can Do

| Capability | Example |
|------------|---------|
| **Auto-scan** | Finds docker-compose, k8s manifests, terraform, Python imports, package.json |
| **Encode** | Runs 6D structural analysis on extracted edges |
| **Explain** | "Your api-gateway is on 89% of all paths — if it goes down, everything fails" |
| **Simulate** | "What if I add a cache between api and database?" → shows structural impact |
| **Compare** | "Show me the drift between v1 and v2 of this architecture" |
| **Recommend** | "Add a circuit breaker upstream of order-service to contain cascading failures" |

## Tools

The agent has 7 tools it calls autonomously:

| Tool | What it does |
|------|-------------|
| `scan_directory` | Auto-detect and extract edges from all infrastructure file types |
| `extract_docker_compose` | Parse a specific docker-compose.yml |
| `extract_kubernetes` | Parse Kubernetes YAML manifests |
| `extract_python_imports` | Build module dependency graph from Python imports |
| `encode_graph` | Run 6D structural encoding on an edge list |
| `encode_and_diff` | Compare two graph versions and show structural drift |
| `simulate_change` | Test hypothetical architecture changes (add/remove edges) |

## Example Session

```
$ semanticembed-agent

SemanticEmbed Agent
========================================
Scanning: .

Found 8 edges from docker-compose.yml:
  frontend -> api, frontend -> auth, api -> postgres, api -> redis,
  api -> auth, auth -> postgres, worker -> redis, worker -> postgres

STRUCTURAL ANALYSIS:
Your architecture has 3 critical risks:

1. **api** is your biggest SPOF (criticality=0.083, independence=0.50).
   It sits on most end-to-end paths and has limited redundancy.
   → Add a fallback API or load balancer.

2. **auth** is a deep bottleneck (depth=0.67, independence=0.00).
   It's the only authentication path — no fallback.
   → Consider an auth cache or backup auth provider.

3. **postgres** is a convergence sink (3 upstream services, 0 downstream).
   If it goes down, api, auth, and worker all fail.
   → Add a read replica for read-heavy services.

> What if I add redis as a cache between api and postgres?

SIMULATED CHANGE: +1 edge (api -> redis-cache -> postgres)

The change reduces postgres convergence pressure:
  - postgres throughput: 0.375 -> 0.286 (reads shifted to cache)
  - api criticality unchanged (still on most paths)
  - New convergence sink: redis-cache (monitor for saturation)

Recommendation: Good change. Reduces database blast radius for reads.
Add a circuit breaker on the redis-cache connection so API falls back
to direct postgres if cache is unavailable.

> quit
```

## Using Programmatically

```python
import asyncio
from agent import run_agent

# Single query
asyncio.run(run_agent(
    "What are the structural risks in this project?",
    path="/path/to/project"
))
```

## Privacy

- The 6D encoding runs server-side (SemanticEmbed API) — your topology edges are sent to the encoding server
- The LLM (Anthropic) sees only the encoding output (6D vectors, risk report) — not your raw code or infrastructure files
- The encoding algorithm is proprietary — neither you nor the LLM ever sees how it works
- Use Ollama for fully local LLM inference if needed (modify the model in agent.py)
