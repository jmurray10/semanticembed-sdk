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

The SDK needs Python 3.10 or newer.

```bash
git clone https://github.com/jmurray10/semanticembed-sdk
cd semanticembed-sdk
pip install -e '.[dev,extract]'
pytest
ruff check .
mypy
```

The dev extras pull in `pytest`, `respx`, `pyyaml`, `ruff`, `mypy`, and
`types-PyYAML`. All HTTP calls in the test suite are respx-mocked — no live
network or credentials needed.

CI runs the tests on Python 3.10–3.14 (Ubuntu) and 3.12 (Windows, macOS),
runs `ruff check .` and `mypy`, and runs the tests once more against the
oldest dependency versions the package allows.

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
6. **Checks pass** — `pytest`, `ruff check .`, and `mypy` are clean, and
   so is the "Check added lines" leak guard ([docs/jev.md](docs/jev.md)).
   PRs from forks get no secrets, so the leak guard fails there; a
   maintainer reviews the added lines by hand instead.

## Releasing (maintainers)

`main` is protected. Every change, releases included, goes through a PR
that must pass CI and the leak guard. There is no direct push to `main`.

1. Open a PR that bumps the version in `pyproject.toml` and
   `src/semanticembed/__init__.py` (`__version__`), and adds the
   CHANGELOG entry.
2. After it merges, tag the merge commit on `main` and push the tag:

   ```bash
   git tag -a vX.Y.Z -m "X.Y.Z" <merge-commit-on-main>
   git push origin vX.Y.Z
   ```

3. The tag starts `publish.yml`. It checks that the tagged commit is on
   `main` and that the tag matches both version strings, runs the tests,
   and builds the package. It then waits for approval on the `pypi`
   environment before uploading through PyPI Trusted Publishing (no token
   to manage).

## Questions

Open a GitHub Discussion or email jeff.murray@alumni.upenn.edu.
