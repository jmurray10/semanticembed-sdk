"""Regressions found by validating the parsers against real public repos
(GoogleCloudPlatform/microservices-demo, terraform-aws-modules/terraform-aws-vpc):

- Terraform references in real modules use count/for_each indexing
  (`aws_subnet.this[0].id`); the ref regex previously matched only
  `type.name.` and missed them.
- Kubernetes manifests often live in non-conventional directories
  (`release/`, `kubernetes-manifests/`); `from_directory` previously only
  scanned a fixed set of dir names.
"""

from __future__ import annotations

import textwrap

from semanticembed import extract


def _write(path, text):
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


class TestTerraformIndexedRefs:
    def test_plain_cross_resource_reference(self, tmp_path):
        _write(tmp_path / "main.tf", """\
            resource "aws_instance" "web" {
              subnet_id = aws_subnet.main.id
            }
            resource "aws_subnet" "main" {
              cidr_block = "10.0.1.0/24"
            }
        """)
        edges = {tuple(e) for e in extract.from_terraform(str(tmp_path))}
        assert ("web", "main") in edges

    def test_count_for_each_indexed_refs(self, tmp_path):
        _write(tmp_path / "vpc.tf", """\
            resource "aws_nat_gateway" "gw" {
              subnet_id     = aws_subnet.public[0].id
              allocation_id = aws_eip.nat[count.index].id
            }
            resource "aws_subnet" "public" {
              count = 2
            }
            resource "aws_eip" "nat" {
              count = 2
            }
        """)
        edges = {tuple(e) for e in extract.from_terraform(str(tmp_path))}
        assert ("gw", "public") in edges     # aws_subnet.public[0].id
        assert ("gw", "nat") in edges        # aws_eip.nat[count.index].id


class TestFromDirectoryK8sDiscovery:
    def test_finds_manifests_in_nonstandard_dir(self, tmp_path):
        rel = tmp_path / "release"
        rel.mkdir()
        _write(rel / "kubernetes-manifests.yaml", """\
            apiVersion: v1
            kind: Service
            metadata:
              name: web
            spec:
              selector:
                app: web
            ---
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: web-deploy
            spec:
              template:
                metadata:
                  labels:
                    app: web
        """)
        edges, sources = extract.from_directory(str(tmp_path))
        assert "kubernetes" in sources
        assert ("web", "web-deploy") in {tuple(e) for e in edges}
