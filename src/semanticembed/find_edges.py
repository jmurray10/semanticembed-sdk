"""Programmatic edge discovery — the agent's extraction loop without the REPL.

Most users want a function, not a chat interface. `find_edges()` runs the
deterministic infrastructure scan first (`extract.from_directory`) and only
falls through to an LLM if no recognized files were found.

This module is the public hook for what the `agent/` CLI does interactively.

Data egress (read README before using `provider="claude"` / `"gemini"` on
private repos): the LLM fallback sends file contents to Anthropic or Google.
Vendored directories (node_modules, .venv, vendor, ...) and files that
resolve outside `path` are skipped, and secret-looking values are replaced
with [REDACTED] first. Redaction is pattern-based and can miss a secret.
The deterministic path (`from_directory`) sends nothing to an LLM.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from . import extract


_LLM_SYSTEM = """You extract directed service-dependency edges from architecture artifacts.
Output ONLY a JSON object with a single key "edges": a list of [source, target] pairs.
Use the exact node names that appear in the source. Drop self-loops. No prose.
"""

_MAX_FILE_BYTES = 60_000  # per file, to control LLM context cost
_MAX_TOTAL_BYTES = 250_000  # across all files in a single LLM call


def find_edges(
    path: str = ".",
    *,
    provider: str = "claude",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    max_nodes: Optional[int] = None,
) -> tuple[list[tuple[str, str]], dict[str, int], list[str]]:
    """Discover directed dependency edges in `path`.

    Returns ``(edges, sources, log)``:

    - ``edges`` — list of ``(source, target)`` tuples
    - ``sources`` — mapping of source name (e.g. ``"docker-compose"``) to edge count
    - ``log`` — human-readable steps taken (extraction path, LLM fallback, truncation)

    Strategy:

    1. Try ``extract.from_directory(path)``. If any edges are found, return them
       (no LLM call, no data egress).
    2. Otherwise fall through to the LLM provider. Read recognized text files
       under ``path`` (capped at ``_MAX_TOTAL_BYTES``) and ask the model for an
       edge list.

    Args:
        path: Directory to scan.
        provider: ``"claude"`` (Anthropic) or ``"gemini"`` (Google). Only used if
            the deterministic scan finds nothing.
        model: Override the default model for the chosen provider.
        api_key: Override the env var for the LLM provider key.
        max_nodes: If set, prune the result to at most this many nodes
            (BFS from the most-cited node), so it fits a known tier limit.

    Raises:
        RuntimeError: if the LLM fallback is triggered but the SDK for that
            provider is not installed, or the API key is missing.
        ValueError: if ``provider`` is unknown.
    """
    log: list[str] = []

    # Step 1 — deterministic scan
    edges, sources = extract.from_directory(path)
    if edges:
        log.append(f"deterministic scan found {len(edges)} edges from {sources}")
        edges = [tuple(e) for e in edges]
        if max_nodes is not None:
            edges = _prune_to_max_nodes(edges, max_nodes, log)
        return edges, sources, log

    log.append("deterministic scan returned no edges; falling back to LLM extraction")

    # Step 2 — LLM fallback
    files = _gather_files(path, log)
    if not files:
        log.append("no readable text files found; nothing to extract")
        return [], {}, log

    if provider == "claude":
        raw_edges = _extract_with_claude(files, model, api_key, log)
        sources = {"claude-llm": len(raw_edges)}
    elif provider == "gemini":
        raw_edges = _extract_with_gemini(files, model, api_key, log)
        sources = {"gemini-llm": len(raw_edges)}
    else:
        raise ValueError(f"Unknown provider: {provider!r} (expected 'claude' or 'gemini')")

    edges = [(str(s), str(t)) for s, t in raw_edges if s != t]
    if max_nodes is not None:
        edges = _prune_to_max_nodes(edges, max_nodes, log)
    return edges, sources, log


# --- Helpers ---------------------------------------------------------------


_SUPPORTED_GLOBS = (
    "**/docker-compose.yml",
    "**/docker-compose.yaml",
    "**/compose.yml",
    "**/compose.yaml",
    "**/k8s/*.yaml",
    "**/kubernetes/*.yaml",
    "**/manifests/*.yaml",
    "**/deploy/*.yaml",
    "**/deployments/*.yaml",
    "**/.github/workflows/*.yml",
    "**/.github/workflows/*.yaml",
    "**/*.tf",
    "**/package.json",
    "**/pyproject.toml",
    "**/Pipfile",
    "**/requirements.txt",
)


# Third-party or generated trees: not the user's architecture, and large.
_SKIP_DIRS = frozenset({
    "node_modules", "bower_components", ".venv", "venv", "site-packages",
    "__pycache__", ".git", ".hg", ".svn", ".terraform", ".tox", ".nox",
    "vendor", ".next",
})

# Values that look like credentials are replaced before file text leaves the
# machine. Edges need names and hosts, never secret values.
_REDACTED = "[REDACTED]"
_TOKEN_RES = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.S),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),                  # AWS access key id
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),                 # GitHub tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),                 # Slack
    re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"),         # Anthropic / OpenAI
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),                      # Google API key
    re.compile(r"\b[rs]k_(?:live|test)_[0-9A-Za-z]{16,}\b"),       # Stripe
    re.compile(r"\bsem_[A-Za-z0-9_-]{16,}\b"),                     # SemanticEmbed
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
]
# user:password@ inside a URL. The host is kept: it is often the edge target.
_URL_CRED_RE = re.compile(r"(\b[A-Za-z][A-Za-z0-9+.-]*://)[^\s:/@'\"]+:[^\s@/'\"]+@")
_SENSITIVE = (
    r"[\w.-]*(?:password|passwd|secret|token|api[_-]?key|apikey|access[_-]?key"
    r"|private[_-]?key|credential|client[_-]?secret)[\w.-]*"
)
# KEY: value / KEY=value / "key": "value" / key = "value"
_ASSIGN_RE = re.compile(
    r"(?im)^(\s*-?\s*[\"']?" + _SENSITIVE + r"[\"']?[ \t]*[:=][ \t]*)(?![ \t,]*$)([^\n]+?)([ \t]*,?[ \t]*)$"
)
# "key": "value" anywhere on a line (minified JSON, YAML flow maps)
_INLINE_PAIR_RE = re.compile(
    r"(?i)([\"']" + _SENSITIVE + r"[\"'][ \t]*:[ \t]*)([\"'])((?:(?!\2).)+)\2"
)
# Kubernetes env entries: "- name: DB_PASSWORD" then "value: ..."
_ENV_PAIR_RE = re.compile(
    r"(?im)^(\s*-?\s*name:[ \t]*[\"']?" + _SENSITIVE + r"[\"']?[ \t]*\n\s*value:[ \t]*)([^\n]+)$"
)
_SECRET_DOC_RE = re.compile(r"(?m)^kind:[ \t]*[\"']?Secret[\"']?[ \t]*$")
_SECRET_REF_PREFIXES = ("${", "{{", "$(", "var.", "local.", "data.", "module.")


def _redact(text: str) -> tuple[str, int]:
    """Replace secret-looking values in config text. Returns (text, count).

    Pattern-based: it can miss a secret. It never removes a host name, so
    service URLs still yield edges.
    """
    count = 0

    # Kubernetes Secret documents: drop every value under data / stringData.
    docs = re.split(r"(?m)^(---.*)$", text)
    for i, doc in enumerate(docs):
        if not _SECRET_DOC_RE.search(doc):
            continue
        lines, in_data = doc.split("\n"), False
        for j, line in enumerate(lines):
            if re.match(r"^(?:data|stringData):\s*$", line):
                in_data = True
                continue
            if in_data and line[:1] in (" ", "\t"):
                m = re.match(r"^(\s+[^:#]+:[ \t]*)(\S.*)$", line)
                if m:
                    lines[j] = m.group(1) + _REDACTED
                    count += 1
            elif line.strip():
                in_data = False
        docs[i] = "\n".join(lines)
    text = "".join(docs)

    def _apply(pattern: re.Pattern, repl, s: str) -> str:
        nonlocal count
        s, n = pattern.subn(repl, s)
        count += n
        return s

    for pattern in _TOKEN_RES:
        text = _apply(pattern, _REDACTED, text)
    text = _apply(_URL_CRED_RE, r"\1" + _REDACTED + "@", text)
    text = _apply(_ENV_PAIR_RE, lambda m: m.group(1) + _REDACTED, text)

    def _assign(m: re.Match) -> str:
        nonlocal count
        value = m.group(2).strip().strip("\"'")
        if not value or _REDACTED in value or value.startswith(_SECRET_REF_PREFIXES):
            return m.group(0)  # empty, already redacted, or a reference to a secret
        count += 1
        return m.group(1) + _REDACTED + m.group(3)

    def _inline(m: re.Match) -> str:
        nonlocal count
        if _REDACTED in m.group(3) or m.group(3).startswith(_SECRET_REF_PREFIXES):
            return m.group(0)
        count += 1
        return m.group(1) + m.group(2) + _REDACTED + m.group(2)

    text = _INLINE_PAIR_RE.sub(_inline, text)
    text = _ASSIGN_RE.sub(_assign, text)
    return text, count


def _gather_files(path: str, log: list[str]) -> list[tuple[str, str]]:
    """Collect (relative_path, content) pairs for LLM context, with budget caps.

    Skips vendored and generated directories, skips files whose real path is
    outside ``path`` (symlinks), and redacts secret-looking values.
    """
    root = Path(path)
    real_root = os.path.realpath(root)
    seen: set[Path] = set()
    out: list[tuple[str, str]] = []
    total = 0
    redacted = 0
    for pattern in _SUPPORTED_GLOBS:
        for fp in root.glob(pattern):
            if fp in seen or not fp.is_file():
                continue
            seen.add(fp)
            rel_parts = fp.relative_to(root).parts
            if any(part in _SKIP_DIRS for part in rel_parts[:-1]):
                continue
            try:
                inside = os.path.commonpath([real_root, os.path.realpath(fp)]) == real_root
            except ValueError:  # different drives on Windows
                inside = False
            if not inside:
                log.append(f"skipped {fp.relative_to(root)}: resolves outside {path}")
                continue
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            content, n = _redact(content)
            redacted += n
            if len(content) > _MAX_FILE_BYTES:
                content = content[:_MAX_FILE_BYTES]
                log.append(f"truncated {fp.relative_to(root)} to {_MAX_FILE_BYTES} bytes")
            if total + len(content) > _MAX_TOTAL_BYTES:
                log.append(
                    f"hit total byte cap ({_MAX_TOTAL_BYTES}); skipping remaining files"
                )
                if redacted:
                    log.append(f"redacted {redacted} secret-looking values before sending")
                return out
            total += len(content)
            try:
                rel = str(fp.relative_to(root))
            except ValueError:
                rel = str(fp)
            out.append((rel, content))
    if redacted:
        log.append(f"redacted {redacted} secret-looking values before sending")
    log.append(f"gathered {len(out)} files, {total} bytes for LLM context")
    return out


def _build_prompt(files: list[tuple[str, str]]) -> str:
    parts = ["Files in this repo:\n"]
    for rel, content in files:
        parts.append(f"\n--- {rel} ---\n{content}")
    parts.append("\n\nReturn only the JSON object: {\"edges\": [[\"a\", \"b\"], ...]}.")
    return "".join(parts)


def _parse_edges_from_text(text: str) -> list[list[str]]:
    text = re.sub(r"```(?:json)?|```", "", text).strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise RuntimeError("LLM response did not contain a JSON object")
    payload = json.loads(match.group())
    edges = payload.get("edges", [])
    return [list(e) for e in edges if isinstance(e, (list, tuple)) and len(e) >= 2]


def _extract_with_claude(
    files: list[tuple[str, str]],
    model: Optional[str],
    api_key: Optional[str],
    log: list[str],
) -> list[list[str]]:
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError(
            "Claude provider requires `anthropic`. Install with: pip install anthropic"
        ) from e
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set and no api_key argument provided")

    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=model or "claude-sonnet-4-6",
        max_tokens=4096,
        system=_LLM_SYSTEM,
        messages=[{"role": "user", "content": _build_prompt(files)}],
    )
    text = msg.content[0].text
    log.append(f"claude returned {len(text)} chars; stop_reason={msg.stop_reason}")
    return _parse_edges_from_text(text)


def _extract_with_gemini(
    files: list[tuple[str, str]],
    model: Optional[str],
    api_key: Optional[str],
    log: list[str],
) -> list[list[str]]:
    try:
        from google import genai
    except ImportError as e:
        raise RuntimeError(
            "Gemini provider requires `google-genai`. Install with: pip install google-genai"
        ) from e
    key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_API_KEY not set and no api_key argument provided")

    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=model or "gemini-2.5-flash",
        contents=_LLM_SYSTEM + "\n\n" + _build_prompt(files),
    )
    text = resp.text or ""
    log.append(f"gemini returned {len(text)} chars")
    return _parse_edges_from_text(text)


def _prune_to_max_nodes(
    edges: list[tuple[str, str]],
    max_nodes: int,
    log: list[str],
) -> list[tuple[str, str]]:
    """Keep edges that touch the top-N most-cited nodes (BFS from the busiest)."""
    if max_nodes <= 0:
        return edges
    nodes = {n for e in edges for n in e}
    if len(nodes) <= max_nodes:
        return edges

    cite_count: Counter[str] = Counter()
    for s, t in edges:
        cite_count[s] += 1
        cite_count[t] += 1
    if not cite_count:
        return edges

    # Build undirected adjacency for BFS.
    adj: dict[str, set[str]] = {}
    for s, t in edges:
        adj.setdefault(s, set()).add(t)
        adj.setdefault(t, set()).add(s)

    seed = cite_count.most_common(1)[0][0]
    keep: set[str] = {seed}
    frontier = [seed]
    while frontier and len(keep) < max_nodes:
        # Visit neighbors in order of citation count (busiest first).
        next_frontier: list[str] = []
        candidates = sorted(
            (n for f in frontier for n in adj.get(f, ()) if n not in keep),
            key=lambda n: -cite_count[n],
        )
        for n in candidates:
            if len(keep) >= max_nodes:
                break
            keep.add(n)
            next_frontier.append(n)
        frontier = next_frontier

    pruned = [(s, t) for s, t in edges if s in keep and t in keep]
    log.append(
        f"pruned to {len(keep)}/{len(nodes)} nodes via BFS from '{seed}', "
        f"{len(pruned)}/{len(edges)} edges retained"
    )
    return pruned
