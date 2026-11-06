# Setup Guide

One install command.

## SemanticEmbed SDK

```bash
pip install -U 'semanticembed[extract]>=0.7.5'
```

This installs the SDK (with `httpx`) and the `[extract]` extra, which adds
`pyyaml` for parsing docker-compose / Kubernetes manifests. Without it, the
deterministic directory scan skips YAML files.

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

## How `--path` finds edges

`--path <dir>` runs the deterministic parsers in `se.extract.from_directory()`
(docker-compose, Kubernetes YAML, GitHub Actions, Terraform, package.json,
pyproject.toml, requirements.txt, and others). No LLM is called and file
contents stay on the machine; only the extracted edge list goes to the
encode API.

For prose, traces, or a custom format, the parent Claude Code agent extracts
the edges itself and passes them with `--edges <json>`. There is no second
LLM in the loop.
