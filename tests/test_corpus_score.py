"""Scorer math. Network clones are not part of unit CI."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "corpus_score.py"
_SPEC = importlib.util.spec_from_file_location("corpus_score", _PATH)
assert _SPEC and _SPEC.loader
score = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(score)


def test_score_sets_perfect_partial_and_empty():
    perfect = score.score_sets([("a", "b")], [["a", "b"]])
    assert perfect["precision"] == 1.0 and perfect["recall"] == 1.0

    partial = score.score_sets([("a", "b"), ("a", "c")], [("a", "b"), ("b", "c")])
    assert partial["hit"] == 1
    assert partial["precision"] == 0.5
    assert partial["recall"] == 0.5
    assert partial["extra"] == [("a", "c")]
    assert partial["missing"] == [("b", "c")]

    empty = score.score_sets([], [])
    assert empty["precision"] == 1.0 and empty["recall"] == 1.0


def test_micro_averages_counts_not_case_means():
    rows = [
        {"hit": 1, "predicted": 1, "gold": 2},
        {"hit": 2, "predicted": 4, "gold": 2},
    ]
    rolled = score.micro(rows)
    assert rolled["cases"] == 2
    assert rolled["precision"] == 3 / 5
    assert rolled["recall"] == 3 / 4


def test_parser_table_covers_the_public_extractors():
    assert set(score.PARSERS) == {
        "docker-compose",
        "kubernetes",
        "github-actions",
        "terraform",
        "cloudformation",
        "aws-cdk",
        "pulumi",
        "python-imports",
        "package-json",
        "package-json-workspaces",
        "otel-traces",
        "langgraph",
        "crewai",
        "autogen",
    }
