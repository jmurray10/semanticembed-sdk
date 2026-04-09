# Setup Guide

Two dependencies. That's it.

## 1. SemanticEmbed SDK

```bash
pip install semanticembed
```

Optional -- set your license key to unlock graphs with more than 50 nodes:
```bash
export SEMANTICEMBED_LICENSE_KEY=se-xxxxxxxxxxxxxxxxxxxx
```

Add to your shell profile to persist:
```bash
echo 'export SEMANTICEMBED_LICENSE_KEY=se-xxxx' >> ~/.zshrc
```

## 2. Ollama with Gemma 4

Install Ollama: https://ollama.com/download

```bash
ollama serve
ollama pull gemma4    # ~16GB, one-time download
```

Verify:
```bash
ollama list
# gemma4    ...
```

## Optional environment variables

```bash
export SEMBED_OLLAMA_URL=http://localhost:11434   # if Ollama is on another host
export SEMBED_MODEL=gemma4                        # to use a different model
```

## Verify everything works

```bash
python3 -c "
import semanticembed
result = semanticembed.encode([('a','b'),('b','c')])
print('SDK OK -- encoding in', result.encoding_time_ms, 'ms')
"
```

```bash
curl -s http://localhost:11434/api/tags | python3 -c "
import sys, json
models = json.load(sys.stdin).get('models', [])
print('Ollama OK --', [m['name'] for m in models])
"
```
