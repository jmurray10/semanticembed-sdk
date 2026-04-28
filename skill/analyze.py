#!/usr/bin/env python3
"""SemanticEmbed analysis script (Claude Code skill).

A thin wrapper over the SDK. The parent Claude Code agent calls this script,
reads the structured output, and reasons about it natively. No local LLM.

Modes:
  --path <dir>       Scan a directory for infrastructure files and encode.
                     Uses se.find_edges() (deterministic; no network egress
                     beyond the encode call to Railway).
  --edges <json>     Encode an explicit edge list.  Format: [["a","b"], ...]
                     Use this when the user describes the architecture in prose
                     -- Claude extracts the edges, this script encodes them.
  --before / --after Drift mode.  Both arguments accept paths or JSON edge lists.

Output:
  Default       Human-readable table (edges, risks, 6D vectors).
  --json        Machine-readable JSON (edges, vectors, risks, metadata).

Environment:
  SEMANTICEMBED_LICENSE_KEY  Unlocks node counts above the 50-node free tier.
  SEMANTICEMBED_API_URL      Override the API endpoint (testing).

Exit codes:
  0  success
  1  bad input (parse error, file not found, no edges supplied)
  2  encode failure (HTTP/connection error)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import semanticembed as se
from semanticembed.exceptions import (
    NodeLimitError,
    SemanticConnectionError,
    SemanticEmbedError,
)


_DIM_NAMES = ("depth", "independence", "hierarchy", "throughput", "criticality", "fanout")


def _vec_dict(vec: Any) -> dict[str, float]:
    if isinstance(vec, list):
        return {d: float(v) for d, v in zip(_DIM_NAMES, vec)}
    if isinstance(vec, dict):
        return {d: float(vec.get(d, 0.0)) for d in _DIM_NAMES}
    return {d: float(getattr(vec, d, 0.0)) for d in _DIM_NAMES}


def _load_edges(arg: str) -> list[list[str]]:
    """Accept a path to a JSON file, a path to a dir (use find_edges), or an inline JSON string."""
    p = Path(arg)
    if p.is_file():
        text = p.read_text(encoding="utf-8", errors="replace")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"ERROR: {arg} is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)
        edges = payload.get("edges", payload) if isinstance(payload, dict) else payload
        if not isinstance(edges, list):
            print(f"ERROR: {arg} did not contain an edge list", file=sys.stderr)
            sys.exit(1)
        return [_norm(e) for e in edges]
    if p.is_dir():
        edges, sources, _log = se.find_edges(str(p))
        if not edges:
            print(f"ERROR: no edges found by deterministic scan of {arg}", file=sys.stderr)
            sys.exit(1)
        print(f"Scanned {arg}: {sources}", file=sys.stderr)
        return [list(e) for e in edges]
    # Inline JSON
    try:
        payload = json.loads(arg)
    except json.JSONDecodeError as e:
        print(f"ERROR: {arg!r} is neither a path nor valid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    edges = payload.get("edges", payload) if isinstance(payload, dict) else payload
    return [_norm(e) for e in edges]


def _norm(e: Any) -> list[str]:
    if isinstance(e, dict):
        s = e.get("source") or e.get("src") or e.get("from")
        t = e.get("target") or e.get("tgt") or e.get("to")
        if not s or not t:
            print(f"ERROR: edge dict missing source/target: {e}", file=sys.stderr)
            sys.exit(1)
        return [str(s), str(t)]
    if isinstance(e, (list, tuple)) and len(e) >= 2:
        return [str(e[0]), str(e[1])]
    print(f"ERROR: bad edge format: {e}", file=sys.stderr)
    sys.exit(1)


def _print_table(edges: list[list[str]], result, risk_report) -> None:
    print(f"\n{'=' * 60}")
    print(f"SemanticEmbed 6D Analysis")
    print(
        f"{result.graph_info['nodes']} nodes  |  {result.graph_info['edges']} edges  "
        f"|  {result.encoding_time_ms:.1f}ms"
    )
    print(f"{'=' * 60}")

    print("\nEDGES")
    for s, t in edges:
        print(f"  {s}  ->  {t}")

    if risk_report.risks:
        print("\nSTRUCTURAL RISKS")
        for r in risk_report.risks:
            sev_marker = {
                "critical": "!!!",
                "high": "!! ",
                "medium": "!  ",
                "warning": "!  ",
            }.get(r.severity, "   ")
            print(f"  {sev_marker} {r.node:<28} {r.category}  ({r.severity})")

    print("\n6D ENCODING (sorted by criticality)")
    rows = sorted(
        result.vectors.items(),
        key=lambda kv: _vec_dict(kv[1])["criticality"],
        reverse=True,
    )
    print(f"  {'node':<28} {'crit':>6} {'tp':>6} {'depth':>6} {'fanout':>6} {'indep':>6}")
    print(f"  {'-' * 28} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6}")
    for node, vec in rows:
        v = _vec_dict(vec)
        print(
            f"  {node:<28} {v['criticality']:>6.3f} {v['throughput']:>6.3f} "
            f"{v['depth']:>6.3f} {v['fanout']:>6.3f} {v['independence']:>6.3f}"
        )
    print()


def _emit_json(edges: list[list[str]], result, risk_report) -> None:
    out = {
        "edges": edges,
        "metadata": result.graph_info,
        "encoding_ms": result.encoding_time_ms,
        "vectors": {n: _vec_dict(v) for n, v in result.vectors.items()},
        "risks": [
            {
                "node": r.node,
                "category": r.category,
                "severity": r.severity,
                "description": r.description,
                "value": r.value,
            }
            for r in risk_report.risks
        ],
    }
    print(json.dumps(out, indent=2))


def _encode_or_exit(edges: list[list[str]]):
    try:
        return se.encode(edges)
    except NodeLimitError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    except SemanticConnectionError as e:
        print(f"ERROR: connection failed: {e}", file=sys.stderr)
        sys.exit(2)
    except SemanticEmbedError as e:
        print(f"ERROR: encode failed: {e}", file=sys.stderr)
        sys.exit(2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SemanticEmbed 6D structural analysis (Claude Code skill helper)",
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--path", help="Directory to scan with se.find_edges()")
    src.add_argument("--edges", help="Inline JSON edge list, path to JSON, or path to a directory")
    parser.add_argument("--before", help="Drift mode: edges or path for the 'before' state")
    parser.add_argument("--after", help="Drift mode: edges or path for the 'after' state")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--edges-only", action="store_true", help="Print extracted edges and exit")
    args = parser.parse_args()

    # License key from env (explicit override only — don't write to module attr globally
    # if not set, so library default key resolution still works).
    license_key = os.environ.get("SEMANTICEMBED_LICENSE_KEY")
    if license_key:
        se.license_key = license_key

    if args.before and args.after:
        before = _load_edges(args.before)
        after = _load_edges(args.after)
        r_before = _encode_or_exit(before)
        r_after = _encode_or_exit(after)
        changes = se.drift(r_before, r_after)
        if args.json:
            print(json.dumps({"drift": changes}, indent=2, default=str))
        else:
            print("\nSTRUCTURAL DRIFT (positive = increased)\n")
            for node, deltas in changes.items():
                print(f"  {node}:")
                for dim, info in deltas.items():
                    print(f"    {dim}: {info['before']:.3f} -> {info['after']:.3f}  ({info['delta']:+.3f})")
        return 0

    if args.path:
        edges = _load_edges(args.path)
    elif args.edges:
        edges = _load_edges(args.edges)
    else:
        print("ERROR: supply --path, --edges, or both --before/--after", file=sys.stderr)
        return 1

    if args.edges_only:
        if args.json:
            print(json.dumps({"edges": edges}, indent=2))
        else:
            for s, t in edges:
                print(f"{s}  ->  {t}")
        return 0

    result = _encode_or_exit(edges)
    risk_report = se.report(result)

    if args.json:
        _emit_json(edges, result, risk_report)
    else:
        _print_table(edges, result, risk_report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
