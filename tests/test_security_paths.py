"""What leaves the machine: file reads stay in the project, secrets are redacted.

Fake credentials are assembled at runtime so no token-shaped string is
committed (secret scanners would flag the test file itself).
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from semanticembed import extract

# The package re-exports the find_edges function under the module's name.
fe = importlib.import_module("semanticembed.find_edges")

GH = "gh" + "p_" + "A1b2C3d4" * 5          # GitHub token shape
AWS = "AK" + "IA" + "ABCDEFGHIJ123456"     # AWS access key id shape
SK = "sk-" + "ant-" + "x9" * 16            # Anthropic key shape
PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n-----END RSA PRIVATE KEY-----"


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted here")


# --- from_requirements: -r stays inside the starting directory (S3) ---------


def test_requirements_include_outside_directory_is_not_read(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "creds.txt").write_text(f"{AWS}\nsecretpkg\n")
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "requirements.txt").write_text(
        "requests\n-r ../outside/creds.txt\n" f"-r {(outside / 'creds.txt').as_posix()}\n"
    )
    edges = extract.from_requirements(str(proj / "requirements.txt"))
    assert edges == [("proj", "requests")]


def test_requirements_include_inside_directory_is_followed(tmp_path):
    proj = tmp_path / "proj"
    (proj / "reqs").mkdir(parents=True)
    (proj / "reqs" / "base.txt").write_text("httpx\n")
    (proj / "requirements.txt").write_text("requests\n-r reqs/base.txt\n")
    assert set(extract.from_requirements(str(proj / "requirements.txt"))) == {
        ("proj", "requests"),
        ("proj", "httpx"),
    }


def test_requirements_symlink_escaping_directory_is_not_read(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "creds.txt").write_text("leakedpkg\n")
    proj = tmp_path / "proj"
    proj.mkdir()
    _symlink_or_skip(proj / "more.txt", outside / "creds.txt")
    (proj / "requirements.txt").write_text("requests\n-r more.txt\n")
    assert extract.from_requirements(str(proj / "requirements.txt")) == [("proj", "requests")]


# --- find_edges LLM fallback: what gets gathered (S4) ------------------------


def test_redact_removes_credentials_but_keeps_hosts():
    text = (
        "services:\n"
        "  api:\n"
        "    environment:\n"
        "      - DB_URL=postgres://admin:hunter2@db:5432/app\n"
        "      - API_TOKEN=abc123xyz\n"
        "      - CART_URL=http://cartservice:7070\n"
        "      - DB_PASSWORD=${DB_PASSWORD}\n"
        f"      - GH={GH}\n"
        f"      - AWS_ACCESS_KEY_ID={AWS}\n"
        "env:\n"
        "  - name: STRIPE_SECRET\n"
        "    value: plainvalue\n"
        "  - name: REDIS_HOST\n"
        "    value: redis\n"
        f'{{"apiKey": "{SK}", "name": "web"}}\n'
        'password = "tfplain"\n'
        "db_password = var.db_password\n"
        f"{PEM}\n"
    )
    out, n = fe._redact(text)
    for secret in ("hunter2", "abc123xyz", GH, AWS, "plainvalue", SK, "tfplain", "MIIEpAIBAAKCAQEA"):
        assert secret not in out, secret
    for kept in ("@db:5432/app", "http://cartservice:7070", "${DB_PASSWORD}", "value: redis",
                 "var.db_password", '"name": "web"'):
        assert kept in out, kept
    assert n >= 8


def test_redact_kubernetes_secret_document():
    text = (
        "apiVersion: v1\nkind: Service\nmetadata:\n  name: api\n---\n"
        "apiVersion: v1\nkind: Secret\nmetadata:\n  name: db-creds\n"
        "data:\n  username: YWRtaW4=\n  password: aHVudGVyMg==\nstringData:\n  url: plain\n"
        "type: Opaque\n"
    )
    out, _ = fe._redact(text)
    assert "YWRtaW4=" not in out and "aHVudGVyMg==" not in out and "url: plain" not in out
    assert "name: db-creds" in out and "name: api" in out and "type: Opaque" in out


def test_gather_skips_vendored_dirs_and_outside_symlinks(tmp_path):
    proj = tmp_path / "proj"
    (proj / "node_modules" / "dep").mkdir(parents=True)
    (proj / "node_modules" / "dep" / "package.json").write_text('{"name": "dep"}')
    (proj / ".venv" / "lib").mkdir(parents=True)
    (proj / ".venv" / "lib" / "pyproject.toml").write_text("[project]\nname='x'\n")
    (proj / "package.json").write_text('{"name": "app", "token": "plaintoken"}')
    outside = tmp_path / "home"
    outside.mkdir()
    (outside / "docker-compose.yml").write_text("services: {secretsvc: {}}\n")
    log: list[str] = []
    try:
        os.symlink(outside / "docker-compose.yml", proj / "docker-compose.yml")
        linked = True
    except (OSError, NotImplementedError):
        linked = False

    files = dict(fe._gather_files(str(proj), log))

    assert set(files) == {"package.json"}
    assert "plaintoken" not in files["package.json"]
    assert any("redacted" in line for line in log)
    if linked:
        assert any("resolves outside" in line for line in log)


def test_find_edges_llm_path_sends_redacted_text(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text(f'{{"name": "app", "apiKey": "{SK}"}}')
    monkeypatch.setattr(extract, "from_directory", lambda path: ([], {}))
    sent = {}

    def fake_claude(files, model, api_key, log):
        sent["files"] = files
        return [("app", "db")]

    monkeypatch.setattr(fe, "_extract_with_claude", fake_claude)
    edges, sources, _ = fe.find_edges(str(tmp_path), provider="claude")
    assert edges == [("app", "db")]
    blob = "".join(content for _, content in sent["files"])
    assert SK not in blob and "[REDACTED]" in blob
