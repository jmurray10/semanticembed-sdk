# License Keys

The SemanticEmbed SDK is free for graphs up to 50 nodes. For larger graphs, activate a license key.

---

## Get a License Key

Email jeff.murray@alumni.upenn.edu with your use case and expected node count.
Public pricing page coming soon.

---

## Activate

**In code:**
```python
import semanticembed
semanticembed.license_key = "se-xxxxxxxxxxxxxxxxxxxx"

# Now up to your plan's node limit
result = semanticembed.encode(large_edges)
```

**Via environment variable:**
```bash
export SEMANTICEMBED_LICENSE_KEY=se-xxxxxxxxxxxxxxxxxxxx
```

**Via config file:**
```bash
echo "se-xxxxxxxxxxxxxxxxxxxx" > ~/.semanticembed/license
```

The SDK uses the first key it finds, in this order:

1. The `license_key=` argument to `encode()` (and the other encode functions).
2. `semanticembed.license_key`.
3. The `SEMANTICEMBED_LICENSE_KEY` environment variable, then `SEMANTICEMBED_API_KEY`.
4. The file `~/.semanticembed/license`.

With no key, requests run on the free tier.

---

## Plans

| Plan | Nodes | Price |
|------|-------|-------|
| **Free** | Up to 50 | $0 |
| **Team** | Up to 500 | Contact us |
| **Enterprise** | Unlimited + continuous monitoring + CI/CD | Contact us |

Enterprise plans include priority support, SLA, and on-prem deployment options.

---

## Questions

Email jeff.murray@alumni.upenn.edu.
