"""Edge audit: ask Jev whether extracted edges are real or parsing artifacts.

Report only. It never changes parser output and never runs in the client
(that would send customer files to a third party). It runs on the public
corpus after scripts/corpus_score.py has cloned it.

Two passes:
  pinned  every edge the parsers extract from the labeled files at the
          pinned commits. All of these are hand-labeled real edges, so any
          "drop" here is a Jev false alarm (measures the audit itself).
  head    edges that appear only at each repo's current HEAD (no labels).
          This is where a parser regression or a new file layout would
          show junk. Needs the <repo>-head checkouts made by the drift step.

For each edge, Jev answers three questions (scripts/jev/questions.py) over
the file text. Code decides (rule fixed in the audit's held-out test):

    target_is_component < NO, or (target_is_group > YES and claim_shown < NO) -> drop
    target_is_component > YES                                                 -> keep
    otherwise                                                                 -> review

Exit 0 after reporting, 2 if Jev could not answer. Drops do not fail the run.

Usage:
    python scripts/corpus_score.py --split all --cache /tmp/semanticembed-corpus
    python scripts/jev/edge_audit.py --cache /tmp/semanticembed-corpus
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from corpus_score import PARSERS, load_manifest  # noqa: E402
from jev_client import Jev, JevError  # noqa: E402
from questions import EDGE_MEANING, EDGE_QUESTIONS, NO, YES  # noqa: E402

WHOLE_FILE_LINES = 80  # shorter files go in whole; longer ones as windows around the names
MAX_EDGES_PER_REQUEST = 25


def decide(a: dict[str, float]) -> str:
    if a["target_is_component"] < NO or (a["target_is_group"] > YES and a["claim_shown"] < NO):
        return "drop"
    if a["target_is_component"] > YES:
        return "keep"
    return "review"


def _tokens(name: str) -> list[str]:
    return [t for t in {name, name.split("/")[-1], name.split(".")[-1]} if len(t) >= 2]


def snippet(path: Path, names: list[str]) -> str:
    """Numbered file text: whole file if short, else lines around each name."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) <= WHOLE_FILE_LINES:
        keep = list(range(len(lines)))
    else:
        hits: set[int] = set()
        for name in names:
            found = 0
            for tok in _tokens(name):
                pat = re.compile(rf"(?<![\w-]){re.escape(tok)}(?![\w-])")
                for i, ln in enumerate(lines):
                    if pat.search(ln):
                        hits.update(range(max(0, i - 2), min(len(lines), i + 3)))
                        found += 1
                    if found >= 4:
                        break
        keep = sorted(hits)[:70]
    out, prev = [], None
    for i in keep:
        if prev is not None and i != prev + 1:
            out.append("...")
        out.append(f"{i + 1}: {lines[i]}")
        prev = i
    return "\n".join(out)


def _edge_questions(parser: str, s: str, t: str, k: int) -> dict[str, dict]:
    claim = EDGE_MEANING[parser].format(s=s, t=t)
    qs = {}
    for qid, q in EDGE_QUESTIONS.items():
        qq = dict(q)
        qq["instructions"] = {"edge": {"source": s, "target": t}, "claim": claim, "question": q["instructions"]}
        qs[f"{qid}__{k}"] = qq
    return qs


def audit_file(jev: Jev, path: Path, rel: str, parser: str, edges: list[tuple[str, str]]) -> list[dict]:
    rows = []
    n_lines = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    if n_lines <= WHOLE_FILE_LINES:
        groups = [edges[i:i + MAX_EDGES_PER_REQUEST] for i in range(0, len(edges), MAX_EDGES_PER_REQUEST)]
        windows = [None] * len(groups)
    else:
        groups = [[e] for e in edges]
        windows = [[e[0], e[1]] for e in edges]
    for group, names in zip(groups, windows, strict=True):
        state = {"file": rel, "snippet": snippet(path, names or [])}
        qs: dict[str, dict] = {}
        for k, (s, t) in enumerate(group):
            qs.update(_edge_questions(parser, s, t, k))
        noul = jev.ask(state, qs)["noul"]
        for k, (s, t) in enumerate(group):
            a = {q: noul[f"{q}__{k}"] for q in EDGE_QUESTIONS}
            rows.append({"file": rel, "parser": parser, "source": s, "target": t, "noul": a, "decision": decide(a)})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, default=HERE.parent.parent / "corpus" / "manifest.json")
    ap.add_argument("--cache", type=Path, default=Path("/tmp/semanticembed-corpus"))
    ap.add_argument("--split", choices=("tuning", "held-out", "all"), default="all")
    ap.add_argument("--skip-pinned", action="store_true")
    ap.add_argument("--log", type=Path)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args(argv)

    manifest = load_manifest(args.manifest)
    cases = [c for c in manifest["cases"]
             if (args.split == "all" or c["split"] == args.split) and c["parser"] in EDGE_MEANING]
    rows: list[dict] = []
    try:
        jev = Jev(log_path=args.log)
    except JevError as e:
        print(f"::error title=Edge audit could not run::{e}")
        return 2
    with jev:
        try:
            for case in cases:
                gold = {tuple(e) for e in case["edges"]}
                pin = args.cache / case["repo"] / case["path"]
                if not args.skip_pinned and pin.is_file():
                    edges = [tuple(e) for e in PARSERS[case["parser"]](str(pin))]
                    for r in audit_file(jev, pin, case["path"], case["parser"], edges):
                        r.update({"pass": "pinned", "case": case["id"], "labeled_real": (r["source"], r["target"]) in gold})
                        rows.append(r)
                head = args.cache / f"{case['repo']}-head" / case["path"]
                if head.is_file():
                    new = [tuple(e) for e in PARSERS[case["parser"]](str(head)) if tuple(e) not in gold]
                    if new:
                        for r in audit_file(jev, head, case["path"], case["parser"], new):
                            r.update({"pass": "head", "case": case["id"], "labeled_real": None})
                            rows.append(r)
        except JevError as e:
            print(f"::error title=Edge audit could not finish::{e}")
            return 2
        cost = f"model {jev.model}, {jev.requests} requests, {jev.input_tokens} input tokens, ${jev.cost_usd:.4f}"

    pinned = [r for r in rows if r["pass"] == "pinned"]
    head_rows = [r for r in rows if r["pass"] == "head"]
    real = [r for r in pinned if r["labeled_real"]]
    false_drops = [r for r in real if r["decision"] == "drop"]
    lines = [
        "## Edge audit (Jev, report only)", "", cost, "",
        f"Pinned, labeled files: {len(pinned)} edges, {len(real)} labeled real. "
        f"Jev would drop {len(false_drops)} real edges and review "
        f"{sum(r['decision'] == 'review' for r in real)}.",
        f"Edges seen only at HEAD: {len(head_rows)}; "
        f"{sum(r['decision'] == 'drop' for r in head_rows)} look like parsing artifacts, "
        f"{sum(r['decision'] == 'review' for r in head_rows)} need review.", "",
    ]
    flagged = [r for r in rows if r["decision"] == "drop" or (r["pass"] == "head" and r["decision"] == "review")]
    if flagged:
        lines += ["| Pass | Case | Edge | Decision | component | group | claim |", "|---|---|---|---|---|---|---|"]
        for r in flagged:
            a = r["noul"]
            lines.append(f"| {r['pass']} | {r['case']} | `{r['source']}` -> `{r['target']}` | {r['decision']} | "
                         f"{a['target_is_component']:.2f} | {a['target_is_group']:.2f} | {a['claim_shown']:.2f} |")
    text = "\n".join(lines) + "\n"
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    if args.json_out:
        args.json_out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
