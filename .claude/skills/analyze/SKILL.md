---
name: analyze
description: Scan a repo for infrastructure files (docker-compose, k8s, terraform, GitHub Actions), extract edges, and run 6D structural risk analysis via SemanticEmbed.
allowed-tools: Bash Read Glob
---

# /analyze — Structural Risk Analysis

Scan the current repository (or a given path) for infrastructure files, extract service dependencies, encode them with SemanticEmbed, and report structural risks.

## Steps

1. **Detect infrastructure files** in the repo. Look for:
   - `docker-compose.yml` / `docker-compose.yaml` / `compose.yml` / `compose.yaml`
   - Kubernetes YAML in `k8s/`, `kubernetes/`, `manifests/`, `deploy/`, or any directory with Service/Deployment resources
   - `.github/workflows/*.yml` (GitHub Actions)
   - `*.tf` files (Terraform)

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

If `se.extract.from_directory` finds nothing but the user pointed to a specific file, use the appropriate parser directly:
- `.yml`/`.yaml` with `services:` key → `se.extract.from_docker_compose(path)`
- `.yml`/`.yaml` with `kind:` key → `se.extract.from_kubernetes(path)`
- `.yml`/`.yaml` with `jobs:` key → `se.extract.from_github_actions(path)`
- `.tf` files → `se.extract.from_terraform(path)`

## Requirements

- `pip install git+https://github.com/jmurray10/semanticembed-sdk.git pyyaml`
- Or if published: `pip install semanticembed pyyaml`
- Free tier: up to 50 nodes (covers most single-service repos)

## Example Output

```
Found 8 edges from: {'docker-compose': 8}

Node          Depth  Indep   Hier   Thru   Crit    Fan
------------------------------------------------------
api           0.333  0.500  0.500  0.500  0.083  0.750
auth          0.667  0.000  0.500  0.375  0.056  0.333
frontend      0.000  0.000  0.500  0.250  0.000  1.000
postgres      1.000  0.500  0.500  0.375  0.000  0.000
redis         0.667  1.000  1.000  0.250  0.000  0.000
worker        0.000  1.000  1.000  0.250  0.000  1.000

STRUCTURAL RISK REPORT
======================
SINGLE POINT OF FAILURE:
  - api    | criticality=0.083, independence=0.50
  - auth   | criticality=0.056, independence=0.00

CONVERGENCE SINK:
  - postgres | 3 upstream services, no downstream
```
