# License Keys

The SemanticEmbed SDK is free for graphs up to 50 nodes. For larger graphs, activate a license key.

---

## Get a License Key

Visit [semanticembed.com/pricing](https://semanticembed.com/pricing) or email jeffmurr@seas.upenn.edu.

---

## Activate

**In code:**
```python
import semanticembed
semanticembed.license_key = "se-xxxxxxxxxxxxxxxxxxxx"

# Now unlimited
result = encode(large_edges)
```

**Via environment variable:**
```bash
export SEMANTICEMBED_LICENSE_KEY=se-xxxxxxxxxxxxxxxxxxxx
```

**Via config file:**
```bash
echo "se-xxxxxxxxxxxxxxxxxxxx" > ~/.semanticembed/license
```

The SDK checks these locations in order: explicit assignment, environment variable, config file.

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

Email jeffmurr@seas.upenn.edu.
