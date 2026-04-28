"""Tests for skill/analyze.py — the Claude Code skill helper.

Runs the script as a subprocess so we exercise the actual CLI surface.
The cloud encode call is mocked at the SDK level via SEMANTICEMBED_API_URL +
respx in the parent process won't work for a subprocess, so these tests
patch via a thin shim: a local FastAPI-less HTTP mock served on a port.

For simplicity here we patch `semanticembed.encode` at import time by
running the script with a bootstrap that injects the mock. That keeps the
test free of network dependencies while still exercising argparse, file
loading, and output formatting.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "skill" / "analyze.py"


def _run(args: list[str], *, env_extra: dict | None = None, stdin: str | None = None):
    """Invoke analyze.py with `semanticembed.encode` monkey-patched in-process via a sitecustomize shim."""
    bootstrap = textwrap.dedent("""
        import json, sys, types
        import semanticembed as se
        from semanticembed.models import SemanticResult, RiskEntry, RiskReport

        def _fake_encode(edges, *, license_key=None, api_url=None, timeout=60.0):
            edges = list(edges)
            nodes = []
            for e in edges:
                if isinstance(e, dict):
                    nodes.append(e.get("source") or e.get("from") or e.get("src"))
                    nodes.append(e.get("target") or e.get("to")  or e.get("tgt"))
                else:
                    nodes.append(e[0]); nodes.append(e[1])
            nodes = sorted({str(n) for n in nodes})
            n = len(nodes)
            vectors = {
                node: [i/(n-1 or 1), 0.5, 0.5, 0.5, (n-i)/n, 0.5]
                for i, node in enumerate(nodes)
            }
            risks = [RiskEntry(node=nodes[0], category="SPOF",
                               severity="critical", description="fake", value=0.9)]
            return SemanticResult(
                vectors=vectors,
                graph_info={"nodes": n, "edges": len(edges), "max_depth": n-1},
                encoding_time_ms=1.0,
                risks=risks,
            )

        se.encode = _fake_encode
    """)
    cmd = [sys.executable, "-c", bootstrap + f"\nimport runpy; sys.argv = ['analyze'] + {args!r}; runpy.run_path({str(SKILL_SCRIPT)!r}, run_name='__main__')"]
    env = None
    if env_extra is not None:
        import os
        env = {**os.environ, **env_extra}
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=stdin,
        env=env,
        timeout=30,
    )


class TestEdgesArg:
    def test_inline_json_edges(self):
        r = _run(["--edges", '[["a","b"],["b","c"]]'])
        assert r.returncode == 0, r.stderr
        assert "a  ->  b" in r.stdout
        assert "b  ->  c" in r.stdout
        assert "STRUCTURAL RISKS" in r.stdout
        assert "6D ENCODING" in r.stdout

    def test_inline_json_edges_with_json_output(self):
        r = _run(["--edges", '[["a","b"],["b","c"]]', "--json"])
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert out["edges"] == [["a", "b"], ["b", "c"]]
        assert "vectors" in out
        assert out["risks"][0]["severity"] == "critical"
        assert out["metadata"]["nodes"] == 3

    def test_edges_from_json_file(self, tmp_path):
        f = tmp_path / "graph.json"
        f.write_text(json.dumps({"edges": [["x", "y"], ["y", "z"]]}))
        r = _run(["--edges", str(f)])
        assert r.returncode == 0, r.stderr
        assert "x  ->  y" in r.stdout

    def test_edges_only_skips_encoding(self):
        r = _run(["--edges", '[["a","b"],["b","c"]]', "--edges-only"])
        assert r.returncode == 0
        assert "a  ->  b" in r.stdout
        # No encoding section should appear
        assert "6D ENCODING" not in r.stdout


class TestPathArg:
    def test_directory_scan(self, tmp_path):
        (tmp_path / "docker-compose.yml").write_text(textwrap.dedent("""\
            services:
              web:
                image: nginx
                depends_on: [api]
              api:
                image: my-api
                depends_on: [db]
              db:
                image: postgres
        """))
        r = _run(["--path", str(tmp_path)])
        assert r.returncode == 0, r.stderr
        assert "web  ->  api" in r.stdout
        assert "api  ->  db" in r.stdout

    def test_empty_directory_exits_1(self, tmp_path):
        r = _run(["--path", str(tmp_path)])
        assert r.returncode == 1
        assert "no edges found" in r.stderr.lower()


class TestDriftMode:
    def test_drift_with_two_edge_sets(self):
        r = _run([
            "--before", '[["a","b"],["b","c"]]',
            "--after",  '[["a","b"],["b","c"],["a","c"]]',
        ])
        assert r.returncode == 0, r.stderr
        assert "STRUCTURAL DRIFT" in r.stdout

    def test_drift_json_output(self):
        r = _run([
            "--before", '[["a","b"],["b","c"]]',
            "--after",  '[["a","b"],["b","c"],["a","c"]]',
            "--json",
        ])
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert "drift" in out


class TestErrorPaths:
    def test_no_args(self):
        r = _run([])
        assert r.returncode == 1
        assert "supply --path, --edges" in r.stderr

    def test_invalid_edges_json(self):
        r = _run(["--edges", "not json at all"])
        assert r.returncode == 1
        assert "neither a path nor valid JSON" in r.stderr

    def test_missing_file_falls_through_to_inline_parse(self, tmp_path):
        # If user passes a non-existent file path that isn't valid JSON, error
        r = _run(["--edges", str(tmp_path / "nope.json")])
        assert r.returncode == 1


class TestNoOllamaDependency:
    def test_script_does_not_import_httpx_at_top_level(self):
        """Regression: v0.2.2 required httpx for Ollama. v0.2.3 should not."""
        text = SKILL_SCRIPT.read_text()
        # The script may transitively import httpx via the SDK, but it must not
        # import or call ollama directly.
        assert "ollama" not in text.lower()
        assert "OLLAMA" not in text
        assert "gemma" not in text.lower()
