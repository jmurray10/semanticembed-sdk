# Setup Guide

One dependency.

## SemanticEmbed SDK

```bash
pip install 'semanticembed[extract]'
```

The `[extract]` extra adds `pyyaml` for parsing docker-compose / Kubernetes
manifests. Without it, the deterministic directory scan can't read YAML, and
you'd be limited to passing edges directly via `--edges`.

## License key (optional)

Free tier covers graphs up to 50 nodes. Above that, set a key:

```bash
export SEMANTICEMBED_LICENSE_KEY=se-xxxxxxxxxxxxxxxxxxxx
```

Add to your shell profile to persist:
```bash
echo 'export SEMANTICEMBED_LICENSE_KEY=se-xxxx' >> ~/.zshrc
```

## Verify

```bash
python3 -c "
import semanticembed
result = semanticembed.encode([('a','b'),('b','c')])
print('SDK OK --', result.encoding_time_ms, 'ms encoding')
"
```

Then run the skill against any directory with infra files:
```bash
python3 /path/to/skill/analyze.py --path .
```

## Optional environment variables

| Variable | Purpose |
|---|---|
| `SEMANTICEMBED_LICENSE_KEY` | Unlocks >50-node graphs |
| `SEMANTICEMBED_API_URL` | Override the API endpoint (testing) |

## What changed in v0.2.3

The skill no longer requires Ollama or any local LLM. Edge extraction now
uses either:

- `--path <dir>`: deterministic scan via `se.find_edges()` (docker-compose,
  k8s YAML, GitHub Actions, Terraform, package.json, pyproject.toml, etc.)
- `--edges <json>`: explicit edges, when you (or Claude) parsed them
  from prose, traces, or a custom format.

The parent Claude Code agent does any natural-language extraction natively --
no second LLM in the loop.
