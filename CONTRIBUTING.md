# Contributing

Thanks for considering a contribution. The SDK is the public face of a
proprietary product, so contribution scope is intentionally narrow.

## What we welcome

- **New edge extractors** in `extract.py` — additional infrastructure formats,
  AI agent frameworks, CI/CD systems. Pure Python, ideally AST or text
  parsing without runtime dependencies on the framework being parsed.
- **Live observability connectors** in `live.py` — third-party APIs that
  expose service-to-service call relationships (Lightstep, AppDynamics,
  New Relic, Grafana Tempo, Sentry, etc.).
- **Bug fixes** in `client.py`, `extract.py`, `live.py`, `dedupe.py`,
  `find_edges.py`.
- **Documentation** — README clarifications, notebook improvements, new
  example fixtures in `examples/`.
- **Test coverage** — additional respx-mocked test cases for edge cases.

## What's out of scope

- The 6D encoding algorithm itself runs server-side and is not part of
  this repository. Any PR proposing changes to encoding math, risk
  thresholds, or scoring rules will be closed.
- Source-code modifications to the bundled console scripts that change
  their published behavior require a coordinated release.
- License changes. The SDK is proprietary; the public source code is for
  adoption velocity, not distribution rights.

## Development setup

```bash
git clone https://github.com/jmurray10/semanticembed-sdk
cd semanticembed-sdk
pip install -e '.[dev,extract]'
pytest
```

The dev extras pull in `pytest`, `respx`, and `pyyaml`. All HTTP calls in
the test suite are respx-mocked — no live network or credentials needed.

## Pull-request checklist

1. **Tests** — every new public function ships with at least one test in
   `tests/`. Use `respx` for any HTTP, never call live APIs.
2. **Type hints** — public APIs annotate arguments and return types.
3. **Docstrings** — public functions have a docstring with a usage
   `Example::` block.
4. **CHANGELOG.md** — add an entry under an "Unreleased" header (we'll
   roll it into the next version on merge).
5. **No new runtime deps** without prior discussion. The SDK keeps a
   minimal footprint (currently just `httpx`).

## Releasing (maintainers)

Tag pushes to `v*` trigger the `publish.yml` workflow, which uses PyPI
Trusted Publishing (no token to manage). Steps:

```bash
# bump version in pyproject.toml AND src/semanticembed/__init__.py
git commit -am "vX.Y.Z: description"
git push
git tag -a vX.Y.Z -m "vX.Y.Z — short summary"
git push origin vX.Y.Z
# workflow builds + publishes within ~2 minutes
```

## Questions

Open a GitHub Discussion or email jeffmurr@seas.upenn.edu.
