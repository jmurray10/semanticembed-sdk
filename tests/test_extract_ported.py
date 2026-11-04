"""Regression tests ported from depgraph-extract for the shared parsers.

These lock generic behavior. They do not name a public repository.
"""

from __future__ import annotations

import textwrap

from semanticembed import extract


def test_pyproject_pep621_optional_and_dependency_groups(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text(textwrap.dedent("""\
        [project]
        name = "Flask"
        dependencies = [
            "blinker>=1.9.0",
            "importlib-metadata>=3.6.0; python_version < '3.10'",
        ]
        [project.optional-dependencies]
        dotenv = ["python-dotenv"]
        [dependency-groups]
        tests = [
            "pytest",
        ]
        [tool.poetry.dependencies]
        python = "^3.9"
        requests = "^2"
    """))
    edges = set(extract.from_pyproject(str(path)))
    assert ("Flask", "blinker") in edges
    assert ("Flask", "importlib-metadata") in edges
    assert ("Flask", "python-dotenv") in edges
    assert ("Flask", "pytest") in edges
    assert ("Flask", "requests") in edges
    assert not any(dst == "python" for _, dst in edges)

    multiline = tmp_path / "groups.toml"
    multiline.write_text(textwrap.dedent("""\
        [project]
        name = "demo"
        [dependency-groups]
        dev = [
            "pkg[extra]>=1",
            "other",
        ]
    """))
    grouped = set(extract.from_pyproject(str(multiline)))
    assert ("demo", "pkg") in grouped
    assert ("demo", "other") in grouped


def test_requirements_skips_editable_self_and_comments(tmp_path):
    path = tmp_path / "requirements-dev.txt"
    path.write_text("# comment\n-e .[socks]\npytest>=2.8.0,<9\nhttpbin~=0.10.0\n")
    edges = set(extract.from_requirements(str(path)))
    assert edges == {
        (tmp_path.name, "pytest"),
        (tmp_path.name, "httpbin"),
    }


def test_terraform_module_refs_stay_inside_their_block(tmp_path):
    (tmp_path / "main.tf").write_text(textwrap.dedent("""\
        resource "aws_kms_key" "this" {
          description = "key"
        }
        resource "random_pet" "this" {
          length = 2
        }
        module "bucket" {
          source = "../../"
          bucket = random_pet.this.id
          kms_key_id = aws_kms_key.this.arn
        }
    """))
    edges = set(extract.from_terraform(str(tmp_path)))
    assert ("aws_kms_key.this", "random_pet.this") not in edges
    assert ("bucket", "random_pet.this") in edges
    assert ("bucket", "aws_kms_key.this") in edges


def test_terraform_heredoc_braces_do_not_end_the_block(tmp_path):
    (tmp_path / "main.tf").write_text(textwrap.dedent("""\
        resource "random_pet" "name" {
          length = 2
        }
        module "table" {
          source = "../../"
          name   = "t-${random_pet.name.id}"
          policy = <<POLICY
        { "Statement": [] }
        POLICY
        }
        resource "aws_iam_role" "extra" {
          name = random_pet.name.id
        }
    """))
    edges = set(extract.from_terraform(str(tmp_path)))
    assert ("table", "name") in edges
    assert ("extra", "name") in edges


def test_zipkin_single_object_uses_remote_endpoint(tmp_path):
    path = tmp_path / "span.json"
    path.write_text(
        '{"traceId":"abc","id":"child","parentId":"missing","kind":"CLIENT",'
        '"localEndpoint":{"serviceName":"frontend"},'
        '"remoteEndpoint":{"serviceName":"backend"}}'
    )
    assert extract.from_otel_traces(str(path)) == [("frontend", "backend")]
    path.write_text(
        '{"traceId":"abc","id":"s","kind":"SERVER",'
        '"localEndpoint":{"serviceName":"backend"},'
        '"remoteEndpoint":{"serviceName":"frontend"}}'
    )
    assert extract.from_otel_traces(str(path)) == [("frontend", "backend")]


def test_jaeger_trace_object_without_data_wrapper(tmp_path):
    path = tmp_path / "trace.json"
    path.write_text(
        '{"traceID":"t","spans":['
        '{"spanID":"a","processID":"p1","references":[]},'
        '{"spanID":"b","processID":"p2","references":[{"refType":"CHILD_OF","spanID":"a"}]}'
        '],"processes":{"p1":{"serviceName":"frontend"},"p2":{"serviceName":"db"}}}'
    )
    assert extract.from_otel_traces(str(path)) == [("frontend", "db")]


def test_langgraph_conditional_edges_without_path_map(tmp_path):
    path = tmp_path / "g.py"
    path.write_text(textwrap.dedent('''\
        from typing import Literal
        from langgraph.graph import StateGraph, START, END
        def route(state) -> Literal["draft", "notify"]:
            if state:
                return "draft"
            return "notify"
        g = StateGraph(dict)
        g.add_node("triage", lambda s: s)
        g.add_node("draft", lambda s: s)
        g.set_entry_point("triage")
        g.add_conditional_edges("triage", route)
        g.add_edge("notify", END)
    '''))
    edges = set(extract.from_langgraph(str(path)))
    assert ("triage", "draft") in edges
    assert ("triage", "notify") in edges
    assert ("START", "triage") in edges


def test_cdk_bare_imported_construct_call(tmp_path):
    path = tmp_path / "app.py"
    path.write_text(textwrap.dedent("""\
        from backend.database import Database
        from backend.api import API
        database = Database(self, "Database", billing="on_demand")
        api = API(self, "API", table=database.table)
        database.table.grant_read_write_data(api.function)
    """))
    edges = set(extract.from_aws_cdk(str(path)))
    assert ("api", "database") in edges
    assert ("database", "api") in edges


def test_pulumi_loop_variable_resource_name(tmp_path):
    path = tmp_path / "main.py"
    path.write_text(textwrap.dedent("""\
        import pulumi_aws as aws
        bucket = aws.s3.Bucket("web")
        for filename in files:
            obj = aws.s3.BucketObject(filename, bucket=bucket.id)
        named = aws.s3.BucketObject(f"web-{suffix}", bucket=bucket.id)
    """))
    edges = set(extract.from_pulumi(str(path)))
    assert ("obj", "bucket") in edges
    assert ("named", "bucket") in edges
    assert not any(node == "filepath" or node == "filename" for edge in edges for node in edge)
