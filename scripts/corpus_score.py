#!/usr/bin/env python3
"""Score hand-labeled public repos against the extractors.

Gold edges live in corpus/manifest.json. Parser names dispatch to
semanticembed.extract. Nothing in here special-cases a repository or a
node name.

Exit status is 0 when every selected case is scored and each extractor is
deterministic on that case. Precision and recall are printed; they are the
measurement, not a hard-coded pass line.

    python scripts/corpus_score.py --split tuning
    python scripts/corpus_score.py --split held-out
    python scripts/corpus_score.py --split all --live-api
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from semanticembed import extract  # noqa: E402

PARSERS = {
    "docker-compose": extract.from_docker_compose,
    "kubernetes": extract.from_kubernetes,
    "github-actions": extract.from_github_actions,
    "terraform": extract.from_terraform,
    "cloudformation": extract.from_cloudformation,
    "aws-cdk": extract.from_aws_cdk,
    "pulumi": extract.from_pulumi,
    "python-imports": extract.from_python_imports,
    "package-json": extract.from_package_json,
    "package-json-workspaces": extract.from_package_json_workspaces,
    "otel-traces": extract.from_otel_traces,
    "langgraph": extract.from_langgraph,
    "crewai": extract.from_crewai,
    "autogen": extract.from_autogen,
}


def score_sets(predicted: list[tuple[str, str]], gold: list[tuple[str, str]]) -> dict:
    """Precision and recall for one edge set. Both empty scores as 1."""
    pred = {tuple(edge) for edge in predicted}
    expected = {tuple(edge) for edge in gold}
    hit = pred & expected
    precision = 1.0 if not pred else len(hit) / len(pred)
    recall = 1.0 if not expected else len(hit) / len(expected)
    return {
        "precision": precision,
        "recall": recall,
        "predicted": len(pred),
        "gold": len(expected),
        "hit": len(hit),
        "extra": sorted(pred - expected),
        "missing": sorted(expected - pred),
    }


def micro(rows: list[dict]) -> dict:
    hit = sum(row["hit"] for row in rows)
    predicted = sum(row["predicted"] for row in rows)
    gold = sum(row["gold"] for row in rows)
    return {
        "cases": len(rows),
        "precision": 1.0 if predicted == 0 else hit / predicted,
        "recall": 1.0 if gold == 0 else hit / gold,
        "hit": hit,
        "predicted": predicted,
        "gold": gold,
    }


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    done = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def checkout(url: str, sha: str, dest: Path) -> None:
    """Fetch one commit into dest. Reuses an existing checkout of that SHA."""
    head_file = dest / ".corpus-sha"
    if head_file.is_file() and head_file.read_text(encoding="utf-8").strip() == sha:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").is_dir():
        if dest.exists():
            raise RuntimeError(f"cache path exists and is not a git checkout: {dest}")
        _run(["git", "init", str(dest)])
        _run(["git", "remote", "add", "origin", url], cwd=dest)
    _run(["git", "fetch", "--depth", "1", "origin", sha], cwd=dest)
    _run(["git", "checkout", "--detach", "--force", "FETCH_HEAD"], cwd=dest)
    head_file.write_text(sha + "\n", encoding="utf-8")


def remote_head(url: str) -> str:
    line = _run(["git", "ls-remote", url, "HEAD"])
    return line.split()[0]


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def selected(manifest: dict, split: str) -> list[dict]:
    cases = manifest["cases"]
    if split == "all":
        return cases
    return [case for case in cases if case["split"] == split]


def run_cases(manifest: dict, cases: list[dict], cache: Path) -> list[dict]:
    repos = {repo["id"]: repo for repo in manifest["repos"]}
    rows = []
    for case in cases:
        repo = repos[case["repo"]]
        dest = cache / repo["id"]
        checkout(repo["url"], repo["sha"], dest)
        parser = PARSERS[case["parser"]]
        target = dest / case["path"]
        first = [tuple(edge) for edge in parser(str(target))]
        second = [tuple(edge) for edge in parser(str(target))]
        if set(first) != set(second):
            raise RuntimeError(f"{case['id']} extractor is not deterministic")
        scored = score_sets(first, [tuple(edge) for edge in case["edges"]])
        scored["id"] = case["id"]
        scored["split"] = case["split"]
        scored["parser"] = case["parser"]
        scored["sha"] = repo["sha"]
        rows.append(scored)
    return rows


def drift_rows(manifest: dict, cases: list[dict], cache: Path) -> list[dict]:
    """Edge-set difference between the pinned SHA and the repo's current HEAD."""
    repos = {repo["id"]: repo for repo in manifest["repos"]}
    seen: set[str] = set()
    out = []
    for case in cases:
        repo = repos[case["repo"]]
        if repo["id"] in seen:
            continue
        seen.add(repo["id"])
        head = remote_head(repo["url"])
        if head == repo["sha"]:
            out.append({"repo": repo["id"], "pinned": repo["sha"], "head": head, "changed_cases": []})
            continue
        pin_dest = cache / repo["id"]
        head_dest = cache / f"{repo['id']}-head"
        checkout(repo["url"], repo["sha"], pin_dest)
        checkout(repo["url"], head, head_dest)
        changed = []
        for item in cases:
            if item["repo"] != repo["id"]:
                continue
            parser = PARSERS[item["parser"]]
            pin_edges = {tuple(edge) for edge in parser(str(pin_dest / item["path"]))}
            head_path = head_dest / item["path"]
            if not head_path.exists():
                changed.append({"id": item["id"], "note": "path missing at HEAD"})
                continue
            head_edges = {tuple(edge) for edge in parser(str(head_path))}
            if pin_edges != head_edges:
                changed.append({
                    "id": item["id"],
                    "added": sorted(head_edges - pin_edges),
                    "removed": sorted(pin_edges - head_edges),
                })
        out.append({"repo": repo["id"], "pinned": repo["sha"], "head": head, "changed_cases": changed})
    return out


def risk_agreement(manifest: dict, split: str, live: bool) -> list[dict]:
    cases = manifest.get("risk_cases", [])
    if split != "all":
        cases = [case for case in cases if case["split"] == split]
    if not live:
        return [{"id": case["id"], "skipped": "pass --live-api to call the hosted encoder"} for case in cases]
    from semanticembed import encode

    rows = []
    for case in cases:
        result = encode(case["edges"])
        again = encode(case["edges"])
        pred = {(item.node, item.category) for item in result.risks}
        pred_again = {(item.node, item.category) for item in again.risks}
        if result.vectors != again.vectors or pred != pred_again:
            raise RuntimeError(f"{case['id']} encode is not deterministic")
        gold = {(item["node"], item["category"]) for item in case["expected"]}
        hit = pred & gold
        union = pred | gold
        rows.append({
            "id": case["id"],
            "split": case["split"],
            "agreement": 1.0 if not union else len(hit) / len(union),
            "hit": sorted(hit),
            "missing": sorted(gold - pred),
            "extra": sorted(pred - gold),
            "encoding_time_ms": result.encoding_time_ms,
            "server_edges": result.graph_info.get("edges"),
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "corpus" / "manifest.json")
    parser.add_argument("--split", choices=("tuning", "held-out", "all"), default="all")
    parser.add_argument("--cache", type=Path, default=Path("/tmp/semanticembed-corpus"))
    parser.add_argument("--live-api", action="store_true")
    parser.add_argument("--skip-drift", action="store_true")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    cases = selected(manifest, args.split)
    rows = run_cases(manifest, cases, args.cache)
    by_split: dict[str, list[dict]] = {}
    for row in rows:
        by_split.setdefault(row["split"], []).append(row)
    summary = {name: micro(group) for name, group in sorted(by_split.items())}
    report = {
        "labeled_on": manifest.get("labeled_on"),
        "split": args.split,
        "summary": summary,
        "cases": rows,
        "drift": [] if args.skip_drift else drift_rows(manifest, cases, args.cache),
        "risk": risk_agreement(manifest, args.split, args.live_api),
    }
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
