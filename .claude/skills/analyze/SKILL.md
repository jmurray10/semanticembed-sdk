---
name: analyze
description: Scan a repo for infrastructure and code files (docker-compose, Kubernetes, Terraform, GitHub Actions, Python and Node.js dependencies, CloudFormation, CDK, Pulumi, agent frameworks), extract edges, and run 6D structural risk analysis via SemanticEmbed.
allowed-tools: Read Glob
---

# /analyze — Structural Risk Analysis

Scan the current repository (or a given path) for infrastructure files, extract service dependencies, encode them with SemanticEmbed, and report structural risks.

## Steps

1. **Detect infrastructure and code files** in the repo. `se.extract.from_directory()` looks for these (source labels in brackets):
   - `docker-compose.yml` / `docker-compose.yaml` / `compose.yml` / `compose.yaml` at the root [`docker-compose`]
   - Kubernetes manifests [`kubernetes`]: detected by content (`apiVersion:` and `kind:`) in any directory, not by directory name
   - `.github/workflows/*.yml` [`github-actions`]
   - `*.tf` files [`terraform`]
   - `*.py` files, module imports [`python-imports`]
   - Root `package.json`, monorepo workspace dependencies [`package-json`]
   - `pyproject.toml` files [`pyproject`]
   - `requirements*.txt` files [`requirements`]
   - OpenTelemetry trace JSON (`traces.json`, `otel.json`, `otlp.json`, `jaeger.json`, `zipkin.json` at the root, or `traces/*.json`) [`otel-traces`]
   - Python files that import LangGraph, CrewAI or AutoGen [`langgraph`, `crewai`, `autogen`]
   - Python files that import AWS CDK or Pulumi [`aws-cdk`, `pulumi`]
   - CloudFormation templates at the root or in `cloudformation/`, `templates/`, `cfn/` [`cloudformation`]

2. **Run the extract + encode script** using the Python snippet below. If the user provided a specific path as an argument, pass it to `from_directory()`. Otherwise use the current directory.

3. **Present the results** clearly:
   - How many edges were found and from which sources
   - The full structural risk report
   - The top 5 most critical nodes with their 6D vectors
   - Specific actionable recommendations based on the risks found

4. **If no infrastructure files are found**, tell the user they can:
   - Point to a specific file: `/analyze path/to/docker-compose.yml`
   - Pass edges manually: `se.encode([("A","B"), ("B","C")])`
   - Use one of the example notebooks

## Python Script

```python
import semanticembed as se

# Auto-detect and extract edges
edges, sources = se.extract.from_directory("TARGET_PATH")

if not edges:
    print("No infrastructure files found.")
else:
    print(f"Found {len(edges)} edges from: {sources}")
    print()

    # Encode
    result = se.encode(edges)

    # Risk report
    print(result.table)
    print()
    print(se.report(result))
```

Replace `TARGET_PATH` with the user's argument or `"."` for current directory.

If `se.extract.from_directory` finds nothing but the user pointed to a specific file or directory, use the appropriate parser directly:
- `.yml`/`.yaml` with `services:` key → `se.extract.from_docker_compose(path)`
- `.yml`/`.yaml` with `kind:` key → `se.extract.from_kubernetes(path)`
- `.yml`/`.yaml` with `jobs:` key → `se.extract.from_github_actions(path)`
- `.tf` files → `se.extract.from_terraform(path)`
- Python directory → `se.extract.from_python_imports(path)`
- `package.json` → `se.extract.from_package_json(path)` or `se.extract.from_package_json_workspaces(path)`
- `pyproject.toml` → `se.extract.from_pyproject(path)`; `requirements.txt` → `se.extract.from_requirements(path)`
- CloudFormation template → `se.extract.from_cloudformation(path)`
- AWS CDK / Pulumi program → `se.extract.from_aws_cdk(path)` / `se.extract.from_pulumi(path)`
- LangGraph / CrewAI / AutoGen file → `se.extract.from_langgraph(path)` / `from_crewai(path)` / `from_autogen(path)`
- OpenTelemetry trace JSON → `se.extract.from_otel_traces(path)`

## Requirements

- `pip install -U 'semanticembed[extract]>=0.7.5'` (from PyPI; installs httpx and pyyaml)
- Free tier: up to 50 nodes (covers most single-service repos)

## Risk categories

The API returns these categories, each with a severity of `critical`, `warning` or `info`:

| Category | Meaning |
|---|---|
| `SINGLE_POINT_OF_FAILURE` | The only option at its pipeline stage |
| `AMPLIFICATION_RISK` | A failure here can cascade to many downstream dependents |
| `CONVERGENCE_SINK` | Many upstream services depend on this one target |
| `DEEP_BOTTLENECK` | A chokepoint deep in the pipeline, hard to diagnose from edge monitoring |
| `MONITORING_GAP_CANDIDATE` | On critical paths but not at the service edge, so it may be missing from dashboards |

The classification runs server-side. Report the category and severity the API returns; don't infer them from the 6D values.

## Example Output

Node names and values are made up. Each risk description comes from the API.

```
Found 7 edges from: {'docker-compose': 7}

Node                                 Depth  Indep   Hier   Thru   Crit    Fan
-----------------------------------------------------------------------------
gateway                              0.250  0.000  0.250  0.300  0.420  0.800
orders                               0.500  0.500  0.500  0.200  0.180  0.600
payments                             0.500  0.500  0.500  0.100  0.120  0.500
queue                                0.750  0.000  0.750  0.100  0.050  0.300
web                                  0.000  0.000  0.250  0.300  0.000  1.000
orders-db                            1.000  0.000  0.750  0.200  0.000  0.000

Key: Depth=pipeline position, Indep=lateral redundancy (0=chokepoint),
     Hier=module/community, Thru=traffic share, Crit=path dependency,
     Fan=broadcaster(1) vs aggregator(0). All values 0-1.

STRUCTURAL RISK REPORT
======================

SINGLE POINT OF FAILURE:
  - gateway                        | <description from the API>

CONVERGENCE SINK:
  - orders-db                      | <description from the API>

WHAT TO DO
----------
  >> gateway: Add a redundant path or fallback service so this node is not the only option at its pipeline stage.
  >> orders-db: Consider adding a read replica, cache layer, or secondary instance so upstream services are not all blocked by one target.

Total: 2 risks (1 critical, 1 warning, 0 info)
```
