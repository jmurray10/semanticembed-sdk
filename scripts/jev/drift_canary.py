"""Drift check for the Jev model behind the leak guard.

Runs the leak guard's questions over fixed, invented cases
(scripts/jev/canary_cases.json) and compares with a stored baseline.

Fails (exit 1) when, compared with the stored baseline for the same model:
  - any case's decision changed (leak / review / pass), or
  - any probability moved more than --max-shift (the thresholds may need a
    new measurement).
Cases whose baseline decision disagrees with their label are known errors;
they are listed in the summary but do not fail the check on their own.
Exit 2 when the check could not run (missing key, API failure).

--also MODEL runs a second model (for example the moving alias
jev-latest) in report-only mode, to see a new release coming before the
pinned model is changed.

Usage:
    python scripts/jev/drift_canary.py
    python scripts/jev/drift_canary.py --also jev-latest
    python scripts/jev/drift_canary.py --write-baseline   # after a deliberate change
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from jev_client import Jev, JevError  # noqa: E402
from leak_guard import decide  # noqa: E402
from questions import LEAK_ALL_QUESTIONS, LEAK_CONTEXT  # noqa: E402

CASES = HERE / "canary_cases.json"
BASELINE = HERE / "canary_baseline.json"
JITTER = 0.05  # repeat calls on the same input move by about this much


def run(model: str | None) -> tuple[str, dict[str, dict[str, float]]]:
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    out: dict[str, dict[str, float]] = {}
    served = model or ""
    with Jev(model=model) as jev:
        for c in cases:
            state = {"file": c["file"], "context": LEAK_CONTEXT, "added_lines": c["added"]}
            ans = jev.ask(state, LEAK_ALL_QUESTIONS)
            out[c["id"]] = ans["noul"]
            served = ans["model"]
        print(f"{model or jev.model}: answered by {served}, {jev.requests} requests, ${jev.cost_usd:.4f}")
    return served, out


def decisions(noul: dict[str, dict[str, float]]) -> dict[str, str]:
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    return {c["id"]: decide(noul[c["id"]], c["file"]) for c in cases}


def evaluate(noul: dict[str, dict[str, float]]) -> list[str]:
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    wrong = []
    for c in cases:
        d = decide(noul[c["id"]], c["file"])
        if c["leak"] and d != "leak":
            wrong.append(f"{c['id']}: leak case decided {d}")
        if not c["leak"] and d == "leak":
            wrong.append(f"{c['id']}: clean case decided leak")
    return wrong


def shifts(noul: dict, base: dict) -> list[tuple[str, str, float]]:
    out = []
    for cid, answers in noul.items():
        for q, p in answers.items():
            if cid in base and q in base[cid]:
                out.append((cid, q, p - base[cid][q]))
    return sorted(out, key=lambda x: -abs(x[2]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--also", help="second model to run in report-only mode, e.g. jev-latest")
    ap.add_argument("--max-shift", type=float, default=0.15)
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args(argv)

    try:
        served, noul = run(None)
        other = run(args.also) if args.also else None
    except JevError as e:
        print(f"::error title=Jev drift check could not run::{e}")
        return 2

    if args.write_baseline:
        BASELINE.write_text(json.dumps({"model": served, "noul": noul}, indent=1, sort_keys=True) + "\n",
                            encoding="utf-8")
        print(f"baseline written for {served}")
        return 0

    lines = ["## Jev drift check", ""]
    status = 0
    wrong = evaluate(noul)
    lines += [f"{len(noul) - len(wrong)} of {len(noul)} cases match their label on {served}."]
    lines += [f"- known error: {w}" for w in wrong] + [""]

    if BASELINE.exists():
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
        if base["model"] != served:
            status = 1
            lines += [f"**Baseline is for {base['model']} but answers came from {served}.** "
                      "Re-measure, then --write-baseline.", ""]
        else:
            now, before = decisions(noul), decisions(base["noul"])
            flipped, jitter = [], []
            for cid, d in now.items():
                if before.get(cid) == d:
                    continue
                moved_by = max(abs(p - base["noul"][cid].get(q, p)) for q, p in noul[cid].items())
                (flipped if moved_by > JITTER else jitter).append(
                    f"{cid}: {before.get(cid)} -> {d} (moved {moved_by:.2f})")
            if flipped:
                status = 1
                lines += ["**Decisions changed since the baseline:**", ""] + [f"- {f}" for f in flipped] + [""]
            if jitter:
                lines += [f"Borderline cases that flipped within run-to-run noise ({JITTER}):"]
                lines += [f"- {f}" for f in jitter] + [""]
            moved = shifts(noul, base["noul"])
            big = [m for m in moved if abs(m[2]) > args.max_shift]
            top = moved[0] if moved else ("-", "-", 0.0)
            lines += [f"Largest shift from baseline: {top[0]}/{top[1]} {top[2]:+.3f} "
                      f"(limit {args.max_shift}).", ""]
            if big:
                status = 1
                lines += ["**Shifts over the limit:**", ""] + [f"- {c}/{q}: {d:+.3f}" for c, q, d in big] + [""]
    else:
        lines += ["No baseline yet: run with --write-baseline.", ""]

    if other:
        o_served, o_noul = other
        o_wrong = evaluate(o_noul)
        lines += [f"Report only: {args.also} is served by {o_served}; "
                  f"{len(o_wrong)} wrong decisions" + (": " + "; ".join(o_wrong) if o_wrong else "."), ""]

    text = "\n".join(lines)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    if status:
        print("::error title=Jev drift::leak guard answers changed; see the summary")
    return status


if __name__ == "__main__":
    sys.exit(main())
