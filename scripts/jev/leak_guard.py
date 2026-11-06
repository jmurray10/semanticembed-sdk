"""Leak guard: flag added lines that explain how the hosted service works inside.

The encoding and risk rules run server-side and are private. Docs may say
what a number or flag MEANS; they must not give a flag's numeric cutoff,
the steps that compute a value, how the input graph is changed before
scoring, or how ties are broken.

For each hunk of added lines in a diff, Jev answers four yes/no questions
(cutoff, processing steps, input-graph changes, tie-breaking) and a subject
question: "does this describe what the hosted server does?". The thresholds
YES and NO are in scripts/jev/questions.py. Code decides:

    any of the four above YES                 -> leak    (error annotation, exit 1)
    otherwise, highest of the four at NO+     -> review  (warning annotation)
    otherwise                                 -> pass

In the guard's own code (GUARD_FILES) a leak also needs the subject answer
at NO or more: that code contains the guard's own cutoffs, which are not
the service's. Everywhere else the subject answer only adds a hint to the
message. See docs/jev.md for the measurements behind this rule.

Exit codes: 0 no leak found, 1 leak found, 2 could not check (missing key,
API failure). A failed check is never reported as a pass.

Usage:
    python scripts/jev/leak_guard.py --base origin/main --head HEAD
    python scripts/jev/leak_guard.py --diff-file pr.diff

Only public diffs may be sent: this runs on pull requests to the public repo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jev_client import Jev, JevError
from questions import LEAK_ALL_QUESTIONS, LEAK_CONTEXT, LEAK_QUESTIONS, LEAK_REASONS, NO, YES

MAX_LINES = 120  # longer runs are split so each request stays focused
OVERLAP = 10     # consecutive pieces share lines so no sentence falls between them

# Exact paths whose added lines are not checked. Binary files need no entry:
# git reports them without hunks. Changes to these paths need owner review
# (CODEOWNERS).
SKIP_PATHS = frozenset({
    "scripts/jev/canary_cases.json",     # invented rules used to test this guard
    "scripts/jev/canary_baseline.json",  # generated probabilities
})


@dataclass
class Hunk:
    file: str
    line: int  # first added line number in the new file
    added: str
    noul: dict[str, float] = field(default_factory=dict)
    decision: str = ""
    error: str = ""


def skipped(path: str) -> bool:
    return path in SKIP_PATHS


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff: str) -> list[Hunk]:
    """Runs of added lines from a unified diff (any context size).

    Hunk bodies are read by the line counts in their @@ header, so an added
    line that itself starts with "++" or "--" is never taken for a header.
    """
    out: list[Hunk] = []
    path: str | None = None
    new_line = start = 0
    old_left = new_left = 0
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        if path and buf and any(x.strip() for x in buf) and not skipped(path):
            step = MAX_LINES - OVERLAP
            for i in range(0, max(len(buf) - OVERLAP, 1), step):
                piece = buf[i:i + MAX_LINES]
                if any(x.strip() for x in piece):
                    out.append(Hunk(path, start + i, "\n".join(piece)))
        buf = []

    # Split on "\n" only: str.splitlines() also breaks on \x0c, \u2028 and
    # similar, which would use up the hunk's line count and drop added lines.
    for raw in diff.split("\n"):
        if raw.endswith("\r"):
            raw = raw[:-1]
        if old_left > 0 or new_left > 0:  # inside a hunk body
            tag = raw[:1]
            if tag == "+":
                if not buf:
                    start = new_line
                buf.append(raw[1:])
                new_line += 1
                new_left -= 1
            elif tag == "-":
                old_left -= 1
            elif tag == "\\":
                pass  # "\ No newline at end of file"
            else:  # context line ends a run of added lines
                flush()
                new_line += 1
                new_left -= 1
                old_left -= 1
            if old_left <= 0 and new_left <= 0:
                flush()
            continue
        if raw.startswith("diff --git "):
            flush()
            path = None
        elif raw.startswith("+++ "):
            target = raw[4:].strip()
            path = None if target == "/dev/null" else re.sub(r"^b/", "", target)
        elif m := _HUNK_RE.match(raw):
            flush()
            old_left = int(m.group(1)) if m.group(1) is not None else 1
            new_line = start = int(m.group(2))
            new_left = int(m.group(3)) if m.group(3) is not None else 1
    flush()
    return out


# The guard's own code states the guard's cutoffs, which read as "a cutoff
# that decides when a flag fires". There a leak also needs the subject check.
# Exact paths: a new file elsewhere in scripts/jev/ gets the normal rule.
GUARD_FILES = frozenset({
    "scripts/jev/leak_guard.py",
    "scripts/jev/drift_canary.py",
    "scripts/jev/edge_audit.py",
    "scripts/jev/jev_client.py",
    "scripts/jev/questions.py",
    "tests/test_jev_scripts.py",
    "docs/jev.md",
})


def decide(noul: dict[str, float], file: str = "") -> str:
    signals = [noul[k] for k in LEAK_QUESTIONS if k in noul]
    if not signals:
        return "pass"
    top = max(signals)
    if top > YES:
        if file not in GUARD_FILES:
            return "leak"
        if noul.get("about_scoring", 1.0) >= NO:  # unknown subject: assume it is
            return "leak"
    if top >= NO:
        return "review"
    return "pass"


def check(hunks: list[Hunk], jev: Jev, workers: int = 4) -> None:
    def one(h: Hunk) -> None:
        state = {"file": h.file, "context": LEAK_CONTEXT, "added_lines": h.added}
        try:
            h.noul = jev.ask(state, LEAK_ALL_QUESTIONS)["noul"]
            h.decision = decide(h.noul, h.file)
        except JevError as e:
            h.error = str(e)
            h.decision = "error"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, hunks))


def git_diff(repo: str, base: str, head: str) -> str:
    out = subprocess.run(
        ["git", "-C", repo, "diff", "--no-color", "--no-ext-diff", "--unified=0", f"{base}...{head}"],
        capture_output=True, check=True,
    ).stdout
    return out.decode("utf-8", errors="replace")  # bytes: keep a lone \r inside a line


def _gh_escape(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _gh_prop(s: str) -> str:
    return _gh_escape(s).replace(":", "%3A").replace(",", "%2C")


def report(hunks: list[Hunk], summary_path: str | None) -> int:
    leaks = [h for h in hunks if h.decision == "leak"]
    reviews = [h for h in hunks if h.decision == "review"]
    errors = [h for h in hunks if h.decision == "error"]

    for h in leaks + reviews:
        top = max(LEAK_QUESTIONS, key=lambda k: h.noul.get(k, 0.0))
        cut = YES if h.decision == "leak" else NO
        reasons = [LEAK_REASONS[k] for k in LEAK_QUESTIONS if h.noul.get(k, 0.0) >= cut]
        level = "error" if h.decision == "leak" else "warning"
        title = "Possible leak of hosted-service internals" if level == "error" else "Leak guard: please review"
        msg = f"This hunk {'; '.join(reasons)} (highest: {top} {h.noul[top]:.2f})."
        if h.noul.get("about_scoring", 1.0) < NO:
            msg += " The subject check reads this as client or user code; a reviewer can confirm."
        print(f"::{level} file={_gh_prop(h.file)},line={h.line},title={title}::{_gh_escape(msg)}")
    for h in errors:
        print(f"::error file={_gh_prop(h.file)},line={h.line},title=Leak guard could not check::"
              f"{_gh_escape(h.error)}")

    lines = [
        "## Leak guard",
        "",
        f"{len(hunks)} hunks of added lines checked: {len(leaks)} leak, {len(reviews)} review, "
        f"{len(errors)} not checked.",
        "",
    ]
    if leaks or reviews or errors:
        lines += ["| Decision | File | Line | threshold | procedure | preprocess | tiebreak | about_scoring |",
                  "|---|---|---|---|---|---|---|---|"]
        for h in leaks + reviews + errors:
            cells = [f"{h.noul.get(k, float('nan')):.2f}" for k in LEAK_ALL_QUESTIONS]
            lines.append(f"| {h.decision} | `{h.file}` | {h.line} | " + " | ".join(cells) + " |")
        lines += ["", "Docs may say what a value or flag means. They must not give a flag's cutoff, "
                  "the steps that compute a value, how the input graph is changed, or how ties are broken."]
    text = "\n".join(lines) + "\n"
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(text)
    print(text)

    if errors:
        return 2
    return 1 if leaks else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--diff-file")
    ap.add_argument("--log", type=Path, help="append every request and answer here (JSONL)")
    ap.add_argument("--json-out", type=Path, help="write per-hunk results here")
    args = ap.parse_args(argv)

    if args.diff_file:
        diff = Path(args.diff_file).read_text(encoding="utf-8", errors="replace")
    elif args.base:
        diff = git_diff(args.repo, args.base, args.head)
    else:
        ap.error("give --base or --diff-file")

    hunks = parse_diff(diff)
    if not hunks:
        print("Leak guard: no added lines to check.")
        return 0
    try:
        jev = Jev(log_path=args.log)
    except JevError as e:
        print(f"::error title=Leak guard could not run::{_gh_escape(str(e))}")
        return 2
    with jev:
        check(hunks, jev)
        print(f"Leak guard: model {jev.model}, {jev.requests} requests, "
              f"{jev.input_tokens} input tokens, ${jev.cost_usd:.4f}")
    if args.json_out:
        args.json_out.write_text(json.dumps([h.__dict__ for h in hunks], indent=1), encoding="utf-8")
    return report(hunks, os.environ.get("GITHUB_STEP_SUMMARY"))


if __name__ == "__main__":
    sys.exit(main())
