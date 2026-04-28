"""Fixture-based tests for semanticembed.extract.

No network calls — these tests parse small fixtures committed to tests/fixtures/.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from semanticembed import extract


FIXTURES = Path(__file__).parent / "fixtures"


class TestDockerCompose:
    def test_parses_depends_on(self):
        edges = extract.from_docker_compose(str(FIXTURES / "docker-compose.yml"))
        edges_set = {tuple(e) for e in edges}
        assert ("frontend", "api") in edges_set
        assert ("frontend", "auth") in edges_set
        assert ("api", "db") in edges_set
        assert ("api", "cache") in edges_set
        assert ("auth", "db") in edges_set
        # 5 dependency edges total
        assert len(edges) == 5


class TestFromDirectory:
    def test_returns_compose_edges_when_present(self, tmp_path):
        (tmp_path / "docker-compose.yml").write_text(textwrap.dedent("""\
            services:
              web:
                image: nginx
                depends_on:
                  - api
              api:
                image: my-api
        """))
        edges, sources = extract.from_directory(str(tmp_path))
        assert ("web", "api") in {tuple(e) for e in edges}
        assert sources.get("docker-compose") == 1

    def test_empty_directory_returns_empty(self, tmp_path):
        edges, sources = extract.from_directory(str(tmp_path))
        assert edges == []
        assert sources == {}

    def test_unrecognized_files_ignored(self, tmp_path):
        (tmp_path / "README.md").write_text("# nothing here")
        (tmp_path / "random.txt").write_text("not infra")
        edges, sources = extract.from_directory(str(tmp_path))
        assert edges == []
        assert sources == {}


class TestFindEdges:
    def test_deterministic_path_skips_llm(self, tmp_path):
        from semanticembed import find_edges
        (tmp_path / "docker-compose.yml").write_text(textwrap.dedent("""\
            services:
              a:
                image: x
                depends_on: [b]
              b:
                image: y
        """))
        edges, sources, log = find_edges(str(tmp_path))
        assert ("a", "b") in {tuple(e) for e in edges}
        assert "docker-compose" in sources
        assert any("deterministic" in entry for entry in log)
        # No LLM keyword in log
        assert not any("claude" in entry or "gemini" in entry for entry in log)

    def test_max_nodes_truncates(self, tmp_path):
        from semanticembed import find_edges
        # docker-compose with 6 services in a chain
        (tmp_path / "docker-compose.yml").write_text(textwrap.dedent("""\
            services:
              a:
                image: x
                depends_on: [b]
              b:
                image: x
                depends_on: [c]
              c:
                image: x
                depends_on: [d]
              d:
                image: x
                depends_on: [e]
              e:
                image: x
                depends_on: [f]
              f:
                image: x
        """))
        edges, sources, log = find_edges(str(tmp_path), max_nodes=3)
        nodes = {n for e in edges for n in e}
        assert len(nodes) <= 3
        assert any("pruned" in entry for entry in log)
