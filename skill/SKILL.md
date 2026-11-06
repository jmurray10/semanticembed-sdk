---
name: semanticembed
description: >
  Run 6D structural analysis on directed graphs -- microservice
  architectures, AI agent pipelines, CI/CD graphs, data workflows. Use
  this skill when the user wants structural risk analysis, single points
  of failure, bottlenecks, vendor concentration, or architecture drift.
  Triggers on: "analyze my pipeline", "find bottlenecks", "which node
  is the SPOF", "structural analysis", "6D encoding", "compare these
  two architectures", or when the user describes a system with nodes
  and connections and asks about fragility.
license: Proprietary. See LICENSE in the semanticembed-sdk repository for complete terms.
compatibility: Requires `pip install -U 'semanticembed[extract]>=0.7.5'` (installs httpx and pyyaml).
metadata:
  author: SemanticEmbed
  version: "0.7.5"
  patent: "Pending -- Application #63/994,075"
---

# SemanticEmbed 6D Structural Analysis

Computes six structural dimensions per node (depth, independence, hierarchy,
throughput, criticality, fanout) and surfaces SPOFs, bottlenecks, amplifiers,
and concentration risks from topology alone. No runtime telemetry needed.

The encoding algorithm runs server-side (Railway). This script is a thin
wrapper over the `semanticembed` Python SDK -- it discovers or accepts edges
locally, then sends only the edge list to the API.

## Step 1: Check the SDK is installed

```bash
python3 -c "import semanticembed; print(semanticembed.__version__)"
```

If that fails, or prints a version older than 0.7.5:
```bash
pip install -U 'semanticembed[extract]>=0.7.5'
```

If the user has a license key, set it once per session:
```bash
export SEMANTICEMBED_LICENSE_KEY=...   # unlocks >50 nodes
```

## Step 2: Pick the input mode

You (Claude) choose based on what the user gave you:

| User provided | Mode |
|---|---|
| A directory path with infra files (docker-compose / k8s / Terraform / `package.json` / `pyproject.toml`) | `--path` |
| A JSON file with edges, or inline JSON | `--edges` |
| A prose description of the system | extract edges yourself, then `--edges` |
| OTel trace JSON | extract parent/child edges yourself, then `--edges` |
| Two states to compare | `--before / --after` |

Why you (Claude) extract edges from prose / traces: the parent agent already
has language understanding. Avoid round-tripping through an extra LLM.

## Step 3: Run the analysis

The script lives at `analyze.py` in this skill's directory. Use the
absolute path resolved from this skill's location.

**Directory scan (deterministic, recommended when applicable):**
Uses only the parsers in `se.extract.from_directory()`. No LLM is called and
file contents stay on the machine; only the extracted edge list is sent.
```bash
python3 {SKILL_DIR}/analyze.py --path /path/to/repo
```

**Inline edges (when extracting from prose / traces):**
```bash
python3 {SKILL_DIR}/analyze.py --edges '[["frontend","auth"],["frontend","api"],["api","db"]]'
```

**Edges from a JSON file:**
```bash
python3 {SKILL_DIR}/analyze.py --edges /path/to/edges.json
```

**Drift between two states:**
```bash
python3 {SKILL_DIR}/analyze.py \
  --before /path/to/repo_before \
  --after  /path/to/repo_after
```

**JSON output (for further reasoning):**
```bash
python3 {SKILL_DIR}/analyze.py --path /path/to/repo --json
```

**Edges only (preview before encoding):**
```bash
python3 {SKILL_DIR}/analyze.py --path /path/to/repo --edges-only
```

## Step 4: Present results

Always show the user:

1. **The edge list** -- so they can confirm the graph was parsed correctly.
2. **Risk flags grouped by severity** (critical first).
3. **The 6D table** sorted by criticality (top 5-10 nodes is usually enough).
4. **A plain-language summary** -- you write this yourself from the data;
   the script doesn't generate prose.

**Severity markers in the script's output:**
- `!!!` critical
- `!  ` warning
- no marker: info

The classification thresholds run server-side; the SDK receives the
severity label, never the threshold values. Trust the label, not a
locally computed cutoff.

**Risk flag meanings:**

| Category | Meaning | Suggested fix |
|---|---|---|
| `SINGLE_POINT_OF_FAILURE` | The only option at its pipeline stage | Add a redundant path or fallback service |
| `AMPLIFICATION_RISK` | A failure here can cascade to many downstream dependents | Add circuit breakers or bulkheads upstream |
| `CONVERGENCE_SINK` | Many upstream services depend on this one target | Add a read replica, cache layer, or secondary instance |
| `DEEP_BOTTLENECK` | A chokepoint deep in the pipeline, hard to diagnose from edge monitoring | Add health checks, timeouts, and dedicated alerting |
| `MONITORING_GAP_CANDIDATE` | On critical paths but not at the service edge, so it may be missing from dashboards | Add dedicated monitoring |

## Step 5: Suggest concrete fixes

Don't just enumerate risks -- propose changes the user can simulate. Example:

> "`stripe` has criticality=0.44 and zero independence -- every checkout depends on
> a single payment provider. Adding `paypal` as a parallel target of `checkout`
> would cut criticality and add lateral redundancy. Want me to run the drift
> analysis with that change?"

Then offer to run drift mode with the proposed change.

## Environment variables

| Variable | Purpose |
|---|---|
| `SEMANTICEMBED_LICENSE_KEY` | License key (unlocks >50 nodes) |
| `SEMANTICEMBED_API_URL` | Override API endpoint (testing only) |

## Trade-secret note

The 6D encoding algorithm runs server-side at the SemanticEmbed Railway endpoint.
The skill sends only the edge list -- node names like `["frontend","auth"]` --
to the API. File contents, source code, and prose descriptions never leave the
local machine through this script. `--path` (and a directory given to
`--edges`, `--before` or `--after`) uses only the deterministic parsers; it
does not call `find_edges()`, whose fallback sends file text to an LLM.

(The optional Claude/Gemini agents in `src/semanticembed/agent/` send your
prompts and their tool results -- edge lists, which parsers found them,
encoding results, error messages -- to Anthropic or Google. They have no
file-read tool. Don't conflate the agent path with the skill.)

See [SETUP.md](SETUP.md) if `import semanticembed` fails.
