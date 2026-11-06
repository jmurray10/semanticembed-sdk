"""scripts/jev: diff parsing, decisions, and failure handling. No network.

The Jev API is replaced by httpx.MockTransport. These tests check the code
that turns probabilities into decisions, not the model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "jev"))

import jev_client
import leak_guard
from questions import LEAK_QUESTIONS

DIFF = """diff --git a/docs/a.md b/docs/a.md
index 1111111..2222222 100644
--- a/docs/a.md
+++ b/docs/a.md
@@ -10,3 +10,5 @@ heading
 context line
+first added
+--- an added line that starts with dashes
-removed line
 more context
+second run
diff --git a/scripts/jev/canary_cases.json b/scripts/jev/canary_cases.json
--- a/scripts/jev/canary_cases.json
+++ b/scripts/jev/canary_cases.json
@@ -1 +1,2 @@
 {
+  "invented": "rule"
diff --git a/gone.txt b/gone.txt
deleted file mode 100644
--- a/gone.txt
+++ /dev/null
@@ -1 +0,0 @@
-bye
"""


def test_parse_diff_runs_lines_and_skips():
    hunks = leak_guard.parse_diff(DIFF)
    assert [(h.file, h.line, h.added) for h in hunks] == [
        ("docs/a.md", 11, "first added\n--- an added line that starts with dashes"),
        ("docs/a.md", 14, "second run"),
    ]


def test_parse_diff_splits_long_runs():
    body = "\n".join(f"+line {i}" for i in range(250))
    diff = f"diff --git a/x.md b/x.md\n--- a/x.md\n+++ b/x.md\n@@ -0,0 +1,250 @@\n{body}\n"
    hunks = leak_guard.parse_diff(diff)
    assert [h.line for h in hunks] == [1, 111, 221]  # pieces overlap by 10 lines
    covered = {h.line + i for h in hunks for i in range(h.added.count("\n") + 1)}
    assert covered == set(range(1, 251))


def test_parse_diff_keeps_lines_with_unusual_breaks():
    """\x0c, \u2028 and a lone \r inside a line must not end the hunk early."""
    diff = (
        "diff --git a/d.md b/d.md\n--- a/d.md\n+++ b/d.md\n@@ -0,0 +1,3 @@\n"
        "+form\x0cfeed\n+line\u2028sep and cr\rinside\n+LAST LINE MUST BE CHECKED\n"
    )
    hunks = leak_guard.parse_diff(diff)
    assert len(hunks) == 1 and hunks[0].added.endswith("LAST LINE MUST BE CHECKED")


def test_parse_diff_handles_crlf_diff_text():
    diff = "diff --git a/d.md b/d.md\r\n--- a/d.md\r\n+++ b/d.md\r\n@@ -0,0 +1,2 @@\r\n+one\r\n+two\r\n"
    assert [h.added for h in leak_guard.parse_diff(diff)] == ["one\ntwo"]


def test_skip_and_guard_lists_are_exact_paths():
    for path in ("notes.lock", "docs/x.pdf", "a/scripts/jev/canary_cases.json"):
        assert not leak_guard.skipped(path)
    assert leak_guard.skipped("scripts/jev/canary_cases.json")
    leak = _n(t=0.9, scope=0.1)
    assert leak_guard.decide(leak, "scripts/jev/new_helper.py") == "leak"
    assert leak_guard.decide(leak, "docs/scripts/jev/leak_guard.py") == "leak"
    assert leak_guard.decide(leak, "scripts/jev/leak_guard.py") == "review"


@pytest.mark.parametrize("bad", [float("nan"), 1.5, -0.1, "x"])
def test_bad_probability_is_an_error(bad):
    def handler(request):
        body = json.loads(request.content)
        answers = {q: {"noul": bad} for q in body["questions"]}
        # json.dumps writes NaN as a bare token, which is what a broken server would send
        return httpx.Response(200, content=json.dumps({"model": "m", "usage": {}, "answers": answers}).encode(),
                              headers={"content-type": "application/json"})
    with _jev(handler) as jev:
        with pytest.raises(jev_client.JevError):
            jev.ask({"x": 1}, LEAK_QUESTIONS)


def test_non_json_body_is_an_error():
    with _jev(lambda r: httpx.Response(200, text="<html>oops</html>")) as jev:
        with pytest.raises(jev_client.JevError, match="unexpected response"):
            jev.ask({"x": 1}, LEAK_QUESTIONS)


def _n(t=0.0, p=0.0, pre=0.0, tie=0.0, scope=0.9):
    return {"threshold": t, "procedure": p, "preprocess": pre, "tiebreak": tie, "about_scoring": scope}


@pytest.mark.parametrize(
    "noul, file, expected",
    [
        (_n(t=0.71), "docs/a.md", "leak"),
        (_n(pre=0.9), "docs/a.md", "leak"),
        (_n(tie=0.9, scope=0.05), "src/semanticembed/report.py", "leak"),  # subject only gates guard files
        (_n(t=0.9, scope=0.29), "scripts/jev/leak_guard.py", "review"),   # guard's own cutoffs
        (_n(t=0.9, scope=0.30), "scripts/jev/leak_guard.py", "leak"),
        (_n(t=0.9, scope=0.1), "tests/test_jev_scripts.py", "review"),
        ({"threshold": 0.95}, "scripts/jev/questions.py", "leak"),         # no subject answer: assume scoring
        (_n(t=0.69), "docs/a.md", "review"),
        (_n(t=0.30), "docs/a.md", "review"),
        (_n(t=0.29, p=0.1, pre=0.2), "docs/a.md", "pass"),
    ],
)
def test_decide(noul, file, expected):
    assert leak_guard.decide(noul, file) == expected


def _jev(handler, **kw):
    return jev_client.Jev(api_key="test-key", transport=httpx.MockTransport(handler), retries=1, **kw)


def _answer(values: dict[str, float]):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == jev_client.PINNED_MODEL
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={
            "model": body["model"],
            "answers": {q: {"noul": values.get(q, 0.01)} for q in body["questions"]},
            "usage": {"input_tokens": 100},
        })
    return handler


def test_leak_hunk_fails_the_check(capsys, monkeypatch):
    monkeypatch.setattr(jev_client.time, "sleep", lambda s: None)
    hunks = leak_guard.parse_diff(DIFF)
    with _jev(_answer({"threshold": 0.93, "about_scoring": 0.9})) as jev:
        leak_guard.check(hunks, jev, workers=1)
        assert jev.requests == 2 and jev.input_tokens == 200
    assert leak_guard.report(hunks, None) == 1
    out = capsys.readouterr().out
    assert "::error file=docs/a.md,line=11," in out
    assert "states a cutoff that decides when a risk flag fires" in out


def test_clean_diff_passes():
    hunks = leak_guard.parse_diff(DIFF)
    with _jev(_answer({})) as jev:
        leak_guard.check(hunks, jev, workers=1)
    assert leak_guard.report(hunks, None) == 0


def test_api_failure_is_an_error_not_a_pass(capsys, monkeypatch):
    monkeypatch.setattr(jev_client.time, "sleep", lambda s: None)
    hunks = leak_guard.parse_diff(DIFF)
    with _jev(lambda r: httpx.Response(503, text="down")) as jev:
        leak_guard.check(hunks, jev, workers=1)
    assert all(h.decision == "error" for h in hunks)
    assert leak_guard.report(hunks, None) == 2
    assert "could not check" in capsys.readouterr().out


def test_missing_answer_is_an_error(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"model": "m", "answers": {"threshold": {"noul": 0.1}}, "usage": {}})
    with _jev(handler) as jev:
        with pytest.raises(jev_client.JevError, match="no answer for"):
            jev.ask({"x": 1}, LEAK_QUESTIONS)


def test_client_error_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, text="bad key")

    with _jev(handler) as jev:
        with pytest.raises(jev_client.JevError, match="401"):
            jev.ask({"x": 1}, LEAK_QUESTIONS)
    assert len(calls) == 1


def test_missing_key_exits_2(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    diff = tmp_path / "d.diff"
    diff.write_text(DIFF)
    assert leak_guard.main(["--diff-file", str(diff)]) == 2
    assert "TYPESAFE_API_KEY is not set" in capsys.readouterr().out


def test_log_never_contains_the_key(tmp_path):
    log = tmp_path / "log.jsonl"
    with _jev(_answer({}), log_path=log) as jev:
        jev.ask({"added_lines": "x"}, LEAK_QUESTIONS)
    text = log.read_text()
    assert "test-key" not in text and '"added_lines": "x"' in text
