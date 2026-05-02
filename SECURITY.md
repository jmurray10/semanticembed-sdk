# Security Policy

## Reporting a vulnerability

If you find a security issue in the SemanticEmbed SDK, please **do not**
open a public GitHub issue. Email **jeffmurr@seas.upenn.edu** with:

- A description of the issue
- Steps to reproduce (minimum working example)
- The SDK version and Python version
- Your proposed fix or mitigation, if any

You'll get an acknowledgement within 72 hours and a fix or status update
within 7 days. Severe issues affecting the cloud encoding service or the
license-key handling path will be prioritized.

## Scope

In scope:
- The published `semanticembed` Python package on PyPI
- The source in this repository, including `client.py`, `extract.py`,
  `live.py`, `find_edges.py`, `dedupe.py`, and the `agent/` CLI
- The PyPI publishing workflow (`.github/workflows/publish.yml`)

Out of scope (please email instead — these are server-side):
- The 6D encoding algorithm and risk-detection logic
- The cloud API at `semanticembed-api-production.up.railway.app`
- The dashboard at `semanticembed-dashboard.vercel.app`

## Supported versions

Only the latest minor version on PyPI receives security fixes. As of this
writing that's the **0.7.x** line. Older versions should upgrade.

## Disclosure

After a fix lands and is published to PyPI, the changelog entry will note
the security implications and credit the reporter unless they prefer to
remain anonymous.
