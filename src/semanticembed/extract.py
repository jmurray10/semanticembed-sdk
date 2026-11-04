"""Extract edges from infrastructure and code files.

Supported formats:
    - docker-compose.yml (depends_on, links)
    - Kubernetes YAML (Service, Deployment, Ingress selectors)
    - GitHub Actions workflows (job needs)
    - Terraform (resource references)
    - Python imports (module dependency graph)
    - package.json (Node.js dependencies, monorepo workspaces)
    - Automatic directory scanning
"""

from __future__ import annotations

import ast
import glob
import os
import re
from pathlib import Path
from typing import Any


def _load_yaml(path: str) -> Any:
    """Load a YAML file. Tries pyyaml, falls back to basic parsing."""
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required for infrastructure parsing. "
            "Install it with: pip install pyyaml"
        )
    with open(path) as f:
        return list(yaml.safe_load_all(f))


def _load_single_yaml(path: str) -> Any:
    """Load a single-document YAML file."""
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required for infrastructure parsing. "
            "Install it with: pip install pyyaml"
        )
    with open(path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Docker Compose
# ---------------------------------------------------------------------------

def from_docker_compose(path: str = "docker-compose.yml") -> list[tuple[str, str]]:
    """Extract service dependency edges from a Docker Compose file.

    Parses ``depends_on`` and ``links`` to build a directed graph of
    service dependencies.

    Args:
        path: Path to docker-compose.yml (or docker-compose.yaml).

    Returns:
        List of (source, target) edge tuples.

    Example::

        edges = se.extract.from_docker_compose("docker-compose.yml")
        result = se.encode(edges)
        print(result.table)
    """
    data = _load_single_yaml(path)
    if not data or "services" not in data:
        raise ValueError(f"No 'services' key found in {path}")

    services = data["services"]
    edges: list[tuple[str, str]] = []

    for svc_name, svc_config in services.items():
        if not isinstance(svc_config, dict):
            continue

        # depends_on can be a list or a dict
        depends = svc_config.get("depends_on", [])
        if isinstance(depends, dict):
            depends = list(depends.keys())
        elif isinstance(depends, str):
            depends = [depends]
        for dep in depends:
            edges.append((svc_name, dep))

        # links
        links = svc_config.get("links", [])
        for link in links:
            target = link.split(":")[0]  # "db:database" -> "db"
            if target != svc_name:
                edges.append((svc_name, target))

    return _dedupe(edges)


# ---------------------------------------------------------------------------
# Kubernetes
# ---------------------------------------------------------------------------

def from_kubernetes(path: str = ".") -> list[tuple[str, str]]:
    """Extract service dependency edges from Kubernetes YAML manifests.

    Scans for Deployment/Service/Ingress resources and infers edges from
    label selectors, service references, and ingress backends. A metadata
    name used by more than one kind is labeled ``Kind/name`` so a Service
    and a Deployment that share a name do not collapse into a self-loop.

    Args:
        path: Path to a YAML file or a directory containing YAML files.

    Returns:
        List of (source, target) edge tuples.

    Example::

        edges = se.extract.from_kubernetes("k8s/")
        result = se.encode(edges)
        print(result.table)
    """
    if os.path.isdir(path):
        files = (
            glob.glob(os.path.join(path, "**/*.yml"), recursive=True)
            + glob.glob(os.path.join(path, "**/*.yaml"), recursive=True)
        )
    else:
        files = [path]

    resources: list[dict] = []
    for f in files:
        try:
            docs = _load_yaml(f)
            for doc in docs:
                if isinstance(doc, dict) and doc.get("kind"):
                    resources.append(doc)
        except Exception:
            continue

    # Index resources by kind
    services: dict[str, dict] = {}
    deployments: dict[str, dict] = {}
    ingresses: list[dict] = []

    for res in resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "")
        if kind == "Service":
            services[name] = res
        elif kind in ("Deployment", "StatefulSet", "DaemonSet"):
            deployments[name] = res
        elif kind == "Ingress":
            ingresses.append(res)

    # When a Service and a workload share a metadata name, a bare label
    # would be a self-loop and get dropped (kubernetes guestbook). Qualify
    # with the kind only for names that are actually shared.
    deployment_kinds: dict[str, str] = {}
    for res in resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "")
        if kind in ("Deployment", "StatefulSet", "DaemonSet") and name:
            deployment_kinds[name] = kind
    name_counts: dict[str, int] = {}
    for name in list(services) + list(deployments) + [
        ing.get("metadata", {}).get("name", "") for ing in ingresses
    ]:
        if name:
            name_counts[name] = name_counts.get(name, 0) + 1

    def _k8s_label(kind: str, name: str) -> str:
        if name_counts.get(name, 0) > 1:
            return f"{kind}/{name}"
        return name

    edges: list[tuple[str, str]] = []

    # Service -> Deployment via selector matching
    for svc_name, svc in services.items():
        svc_selector = svc.get("spec", {}).get("selector", {})
        if not svc_selector:
            continue
        for dep_name, dep in deployments.items():
            dep_labels = (
                dep.get("spec", {})
                .get("template", {})
                .get("metadata", {})
                .get("labels", {})
            )
            if _selectors_match(svc_selector, dep_labels):
                edges.append((
                    _k8s_label("Service", svc_name),
                    _k8s_label(deployment_kinds.get(dep_name, "Deployment"), dep_name),
                ))

    # Ingress -> Service via backend references
    for ing in ingresses:
        ing_name = ing.get("metadata", {}).get("name", "ingress")
        rules = ing.get("spec", {}).get("rules", [])
        for rule in rules:
            paths = rule.get("http", {}).get("paths", [])
            for p in paths:
                backend = p.get("backend", {})
                svc_ref = backend.get("service", {}).get("name") or backend.get("serviceName")
                if svc_ref:
                    target = _k8s_label("Service", svc_ref) if svc_ref in services else svc_ref
                    edges.append((_k8s_label("Ingress", ing_name), target))

    # Env var references between deployments (SERVICE_HOST patterns)
    for dep_name, dep in deployments.items():
        containers = (
            dep.get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("containers", [])
        )
        for container in containers:
            for env in container.get("env", []):
                val = env.get("value", "")
                if isinstance(val, str):
                    for svc_name in services:
                        if svc_name in val and svc_name != dep_name:
                            edges.append((
                                _k8s_label(deployment_kinds.get(dep_name, "Deployment"), dep_name),
                                _k8s_label("Service", svc_name),
                            ))

    return _dedupe(edges)


def _selectors_match(selector: dict, labels: dict) -> bool:
    """Check if all selector key-value pairs exist in labels."""
    if not selector or not labels:
        return False
    return all(labels.get(k) == v for k, v in selector.items())


# ---------------------------------------------------------------------------
# GitHub Actions
# ---------------------------------------------------------------------------

def from_github_actions(path: str = ".github/workflows") -> list[tuple[str, str]]:
    """Extract job dependency edges from GitHub Actions workflow files.

    Parses ``needs`` fields to build a directed graph of CI/CD job
    dependencies.

    Args:
        path: Path to a workflow YAML file or the workflows directory.

    Returns:
        List of (source, target) edge tuples.

    Example::

        edges = se.extract.from_github_actions()
        result = se.encode(edges)
        print(result.table)
    """
    if os.path.isdir(path):
        files = glob.glob(os.path.join(path, "*.yml")) + glob.glob(
            os.path.join(path, "*.yaml")
        )
    else:
        files = [path]

    edges: list[tuple[str, str]] = []

    for f in files:
        try:
            data = _load_single_yaml(f)
        except Exception:
            continue
        if not data or not isinstance(data, dict):
            continue

        workflow_name = data.get("name", Path(f).stem)
        jobs = data.get("jobs", {})

        for job_name, job_config in jobs.items():
            if not isinstance(job_config, dict):
                continue
            needs = job_config.get("needs", [])
            if isinstance(needs, str):
                needs = [needs]

            qualified = f"{workflow_name}/{job_name}"
            if needs:
                for dep in needs:
                    edges.append((f"{workflow_name}/{dep}", qualified))
            else:
                # Root job triggered by workflow
                edges.append((workflow_name, qualified))

    return _dedupe(edges)


# ---------------------------------------------------------------------------
# Terraform
# ---------------------------------------------------------------------------

def from_terraform(path: str = ".") -> list[tuple[str, str]]:
    """Extract resource dependency edges from Terraform files.

    Parses ``resource`` blocks and finds cross-resource references
    (``resource_type.resource_name``) to infer dependencies.

    Args:
        path: Path to a .tf file or a directory containing .tf files.

    Node labels are the resource name (``web``) when that name is unique in
    the scanned files. When several resources share a name — the ``this``
    convention in terraform-aws-modules — the label is ``type.name``
    (``aws_vpc.this``) so those resources do not collapse into one node.
    Distinct keys raise the node count; real modules often pass the free-tier
    50-node cap once names are disambiguated.

    Returns:
        List of (source, target) edge tuples. The source is the resource
        that contains the reference; the target is the resource it references.

    Example::

        edges = se.extract.from_terraform("infra/")
        result = se.encode(edges)
        print(result.table)
    """
    if os.path.isdir(path):
        files = glob.glob(os.path.join(path, "**/*.tf"), recursive=True)
    else:
        files = [path]

    # Collect all resource names
    resource_pattern = re.compile(
        r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{', re.MULTILINE
    )
    # Match `type.name` optionally followed by a `[index]` (count / for_each),
    # e.g. `aws_subnet.this[0].id` or `aws_eip.nat[count.index].id`.
    ref_pattern = re.compile(r"(\w+\.\w+)(?:\[[^\]]*\])?\.")

    resources: dict[str, str] = {}  # "type.name" -> short label
    file_contents: dict[str, str] = {}

    for f in files:
        try:
            with open(f) as fh:
                content = fh.read()
        except Exception:
            continue
        file_contents[f] = content
        for match in resource_pattern.finditer(content):
            res_type, res_name = match.group(1), match.group(2)
            full_name = f"{res_type}.{res_name}"
            resources[full_name] = res_name

    # Bare names collide across resource types (`aws_vpc.this` and
    # `aws_internet_gateway.this`). Count distinct type.name keys, then
    # expand every colliding short name to type.name.
    name_counts: dict[str, int] = {}
    for short in resources.values():
        name_counts[short] = name_counts.get(short, 0) + 1
    for full, short in list(resources.items()):
        if name_counts[short] > 1:
            resources[full] = full

    # Find references between resources
    edges: list[tuple[str, str]] = []
    for f, content in file_contents.items():
        # Split by resource blocks
        blocks = re.split(r'(resource\s+"[^"]+"\s+"[^"]+"\s*\{)', content)
        current_resource = None
        for block in blocks:
            res_match = resource_pattern.match(block.strip())
            if res_match:
                current_resource = f"{res_match.group(1)}.{res_match.group(2)}"
                continue
            if current_resource and current_resource in resources:
                for ref_match in ref_pattern.finditer(block):
                    ref = ref_match.group(1)
                    if ref in resources and ref != current_resource:
                        src_label = resources[current_resource]
                        dst_label = resources[ref]
                        edges.append((src_label, dst_label))

    return _dedupe(edges)


# ---------------------------------------------------------------------------
# Python imports
# ---------------------------------------------------------------------------

def from_python_imports(path: str = ".", *, depth: int | None = None) -> list[tuple[str, str]]:
    """Extract module dependency edges from Python import statements.

    Scans ``.py`` files and builds a directed graph of which modules import
    which. Only includes edges between modules that exist in the scanned
    directory (ignores stdlib and third-party imports).

    Args:
        path: Path to a Python file or directory of Python files.
        depth: How aggressively to roll up module names to service boundaries.

            - ``None`` (default): use the last component of each module path.
              ``myapp.auth.user`` -> ``user``. Backwards-compatible.
            - ``1``: keep only the top-level package. ``myapp.auth.user`` ->
              ``myapp``. Edges between submodules of the same top-level package
              collapse to self-loops and are dropped. Useful for monorepos
              where the top-level dirs are services.
            - ``2``: first two components. ``services.auth.user`` ->
              ``services.auth``. Useful when services live one level down,
              e.g. ``services/auth/``, ``services/payments/``.
            - ``N`` for any N: first N components.

    Returns:
        List of (importer, imported) edge tuples using rolled-up module names.

    Example::

        # Default: short names
        edges = se.extract.from_python_imports("src/")

        # Service-boundary rollup for a monorepo with services/<svc>/...
        edges = se.extract.from_python_imports(".", depth=2)

        result = se.encode(edges)
    """
    if os.path.isfile(path):
        files = [path]
        base = os.path.dirname(os.path.abspath(path))
    else:
        files = glob.glob(os.path.join(path, "**/*.py"), recursive=True)
        base = os.path.abspath(path)

    # Build set of local module names from file paths
    local_modules: set[str] = set()
    file_to_module: dict[str, str] = {}
    for f in files:
        rel = os.path.relpath(f, base).replace(os.sep, "/")
        # Convert path to module name
        if rel.endswith("/__init__.py"):
            mod = rel[:-12].replace("/", ".")
        elif rel.endswith(".py"):
            mod = rel[:-3].replace("/", ".")
        else:
            continue
        # Skip hidden/test/venv directories
        parts = mod.split(".")
        if any(p.startswith(".") or p == "__pycache__" for p in parts):
            continue
        local_modules.add(mod)
        # Also add each parent package
        for i in range(1, len(parts)):
            local_modules.add(".".join(parts[:i]))
        file_to_module[f] = mod

    from_re = re.compile(r"^\s*from\s+(\.*)([\w.]*)\s+import\b", re.MULTILINE)
    import_re = re.compile(r"^\s*import\s+([\w.]+)", re.MULTILINE)
    file_is_package = {
        f: f.replace("\\", "/").endswith("/__init__.py") or f.endswith("__init__.py")
        for f in file_to_module
    }

    def _resolve_import(src_mod: str, is_package: bool, imported: str) -> str | None:
        """Map an import string to a local module, or None."""
        if imported.startswith("."):
            dots = len(imported) - len(imported.lstrip("."))
            rest = imported.lstrip(".")
            current = src_mod if is_package else (
                src_mod.rsplit(".", 1)[0] if "." in src_mod else ""
            )
            parts = current.split(".") if current else []
            levels_up = dots - 1
            if levels_up:
                if levels_up > len(parts):
                    return None
                parts = parts[:-levels_up]
            if rest:
                parts.extend(p for p in rest.split(".") if p)
            candidate = ".".join(parts)
            if candidate in local_modules and candidate != src_mod:
                return candidate
            return None

        parts = imported.split(".")
        candidates = [parts]
        if len(parts) > 1:
            candidates.append(parts[1:])
        for candidate_parts in candidates:
            for i in range(len(candidate_parts), 0, -1):
                candidate = ".".join(candidate_parts[:i])
                if candidate in local_modules and candidate != src_mod:
                    return candidate
        return None

    edges: list[tuple[str, str]] = []
    for f, src_mod in file_to_module.items():
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except Exception:
            continue

        imported_names: list[str] = []
        for match in from_re.finditer(content):
            dots, rest = match.group(1), match.group(2)
            imported_names.append(f"{dots}{rest}" if dots else rest)
        for match in import_re.finditer(content):
            imported_names.append(match.group(1))

        for imported in imported_names:
            if not imported:
                continue
            target = _resolve_import(src_mod, file_is_package[f], imported)
            if not target:
                continue
            if depth is None:
                src_short = src_mod.split(".")[-1]
                dst_short = target.split(".")[-1]
                if src_short == dst_short:
                    src_short = src_mod
                    dst_short = target
                edges.append((src_short, dst_short))
            else:
                src_roll = ".".join(src_mod.split(".")[:depth])
                dst_roll = ".".join(target.split(".")[:depth])
                edges.append((src_roll, dst_roll))

    # _dedupe drops self-loops (which depth rollup naturally creates within
    # a single top-level package) and exact duplicates.
    return _dedupe(edges)


# ---------------------------------------------------------------------------
# package.json (Node.js)
# ---------------------------------------------------------------------------

def from_package_json(path: str = "package.json") -> list[tuple[str, str]]:
    """Extract dependency edges from a package.json file.

    Parses ``dependencies``, ``devDependencies``, and ``peerDependencies``.
    The project name is the source node, each dependency is a target.

    Args:
        path: Path to package.json.

    Returns:
        List of (project, dependency) edge tuples.

    Example::

        edges = se.extract.from_package_json("package.json")
        result = se.encode(edges)
        print(result.table)
    """
    import json as _json

    with open(path) as f:
        data = _json.load(f)

    project_name = data.get("name", "project")
    edges: list[tuple[str, str]] = []

    for dep_key in ("dependencies", "devDependencies", "peerDependencies"):
        deps = data.get(dep_key, {})
        if not isinstance(deps, dict):
            continue
        for dep_name in deps:
            edges.append((project_name, dep_name))

    return _dedupe(edges)


def from_package_json_workspaces(path: str = ".") -> list[tuple[str, str]]:
    """Extract inter-package dependency edges from a monorepo with workspaces.

    Scans all package.json files in the workspace and finds edges between
    local packages (where one workspace package depends on another).

    Args:
        path: Root directory of the monorepo.

    Returns:
        List of (package, dependency) edge tuples between local packages.

    Example::

        edges = se.extract.from_package_json_workspaces(".")
        result = se.encode(edges)
        print(result.table)
    """
    import json as _json

    pkg_files = glob.glob(os.path.join(path, "**/package.json"), recursive=True)

    # Build index of local package names
    local_packages: dict[str, str] = {}  # name -> path
    package_data: dict[str, dict] = {}  # name -> parsed json

    for pf in pkg_files:
        # Skip node_modules
        if "node_modules" in pf:
            continue
        try:
            with open(pf) as f:
                data = _json.load(f)
        except Exception:
            continue
        name = data.get("name")
        if name:
            local_packages[name] = pf
            package_data[name] = data

    # Find edges between local packages
    edges: list[tuple[str, str]] = []
    for pkg_name, data in package_data.items():
        for dep_key in ("dependencies", "devDependencies", "peerDependencies"):
            deps = data.get(dep_key, {})
            if not isinstance(deps, dict):
                continue
            for dep_name in deps:
                if dep_name in local_packages and dep_name != pkg_name:
                    edges.append((pkg_name, dep_name))

    return _dedupe(edges)


# ---------------------------------------------------------------------------
# Infrastructure-as-code: CloudFormation, AWS CDK (Python), Pulumi (Python)
# ---------------------------------------------------------------------------


def from_cloudformation(path: str) -> list[tuple[str, str]]:
    """Extract resource dependency edges from a CloudFormation template.

    Edges represent dependency: a resource's ``DependsOn`` list AND any
    intrinsic references (``Ref``, ``Fn::GetAtt``, ``Fn::Sub``) inside its
    Properties produce a ``this_resource -> referenced_resource`` edge.

    Accepts either YAML (``.yaml`` / ``.yml``) or JSON templates. Pass a
    directory to merge edges across all templates within it.

    Args:
        path: Path to a single template OR a directory of templates.

    Returns:
        Deduped list of ``(dependent, dependency)`` edges.

    Example::

        edges = se.extract.from_cloudformation("infra/")
        result = se.encode(edges)
    """
    files: list[str] = []
    is_dir = os.path.isdir(path)
    if is_dir:
        for ext in ("*.yaml", "*.yml", "*.json", "*.template"):
            files.extend(glob.glob(os.path.join(path, "**", ext), recursive=True))
    elif os.path.isfile(path):
        files = [path]

    edges: list[tuple[str, str]] = []
    for fp in files:
        # When scanning a directory we may pick up arbitrary YAML/JSON that isn't
        # CFN — gate on a cheap header probe so we don't load every k8s manifest
        # / service definition / npm config in the tree.
        if is_dir:
            try:
                with open(fp, encoding="utf-8", errors="replace") as fh:
                    head = fh.read(2048)
            except OSError:
                continue
            if (
                "AWSTemplateFormatVersion" not in head
                and '"Resources"' not in head
                and "\nResources:" not in head
                and not head.lstrip().startswith("Resources:")
            ):
                continue
        try:
            doc = _load_cfn_doc(fp)
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        resources = doc.get("Resources") or doc.get("resources")
        if not isinstance(resources, dict):
            continue
        for res_name, res_config in resources.items():
            if not isinstance(res_config, dict):
                continue
            # Explicit DependsOn
            dep = res_config.get("DependsOn") or res_config.get("dependsOn")
            if isinstance(dep, str):
                edges.append((res_name, dep))
            elif isinstance(dep, list):
                for d in dep:
                    if isinstance(d, str):
                        edges.append((res_name, d))
            # Implicit references inside Properties
            props = res_config.get("Properties") or res_config.get("properties") or {}
            for ref in _cfn_walk_refs(props, set(resources.keys())):
                if ref != res_name:
                    edges.append((res_name, ref))

    return _dedupe(edges)


def _load_cfn_doc(path: str):
    """Load a CFN template — JSON if .json, else YAML (with intrinsic-tag support)."""
    if path.endswith(".json"):
        import json
        with open(path) as f:
            return json.load(f)
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required to parse CloudFormation templates.")

    # CFN YAML uses short intrinsic tags like `!Ref` and `!GetAtt`. The default
    # SafeLoader chokes on these; we register no-op constructors that yield a
    # tagged dict so the walker can detect them.
    class _CfnLoader(yaml.SafeLoader):
        pass

    def _intrinsic_constructor(tag):
        def _ctor(loader, node):
            if isinstance(node, yaml.ScalarNode):
                return {tag: loader.construct_scalar(node)}
            if isinstance(node, yaml.SequenceNode):
                return {tag: loader.construct_sequence(node, deep=True)}
            if isinstance(node, yaml.MappingNode):
                return {tag: loader.construct_mapping(node, deep=True)}
            return None
        return _ctor

    for short in ("Ref", "GetAtt", "Sub", "Join", "Select", "Split",
                  "FindInMap", "ImportValue", "If", "And", "Or", "Not", "Equals",
                  "Base64", "Cidr", "Transform", "Condition"):
        _CfnLoader.add_constructor(f"!{short}", _intrinsic_constructor(f"Fn::{short}"))
    _CfnLoader.add_constructor("!Ref", _intrinsic_constructor("Ref"))

    with open(path) as f:
        return yaml.load(f, Loader=_CfnLoader)


def _cfn_walk_refs(obj, valid_names: set[str]) -> set[str]:
    """Walk a Properties object and collect resource names referenced via
    Ref / Fn::GetAtt / Fn::Sub. Only names that exist as Resources in the
    template are returned."""
    found: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "Ref" and isinstance(v, str) and v in valid_names:
                found.add(v)
            elif k == "Fn::GetAtt":
                # Ref form: ["LogicalName", "Attribute"] OR "LogicalName.Attribute"
                if isinstance(v, list) and v and isinstance(v[0], str):
                    if v[0] in valid_names:
                        found.add(v[0])
                elif isinstance(v, str):
                    name = v.split(".")[0]
                    if name in valid_names:
                        found.add(name)
            elif k == "Fn::Sub":
                # `${LogicalName}` or `${LogicalName.Attribute}`
                template = v[0] if isinstance(v, list) and v else v
                if isinstance(template, str):
                    found.update(_extract_sub_refs(template, valid_names))
            else:
                found.update(_cfn_walk_refs(v, valid_names))
    elif isinstance(obj, list):
        for item in obj:
            found.update(_cfn_walk_refs(item, valid_names))
    return found


def _extract_sub_refs(template: str, valid_names: set[str]) -> set[str]:
    """Pull `${Foo}` / `${Foo.Bar}` references out of a Fn::Sub string."""
    out: set[str] = set()
    for m in re.finditer(r"\$\{([A-Za-z][A-Za-z0-9]*)(?:\.[A-Za-z0-9]+)?\}", template):
        name = m.group(1)
        if name in valid_names:
            out.add(name)
    return out


def from_aws_cdk(path: str) -> list[tuple[str, str]]:
    """Extract construct dependency edges from an AWS CDK Python file.

    Recognizes common patterns where a construct receives other constructs
    via keyword arguments:

    - ``fn = aws_lambda.Function(self, "Fn", role=my_role, vpc=my_vpc)``
        emits ``fn -> my_role`` and ``fn -> my_vpc``.
    - Any kwarg whose value is a Name/Attribute referring to a previously
      assigned construct variable produces an edge.

    TypeScript CDK is not supported in this release.

    Args:
        path: Path to a Python CDK app file.

    Returns:
        Deduped list of ``(construct, dependency)`` edges.
    """
    return _python_resource_graph(path, _looks_like_cdk_call)


def from_pulumi(path: str) -> list[tuple[str, str]]:
    """Extract resource dependency edges from a Pulumi Python program.

    Pulumi resource constructors look like CDK constructs but with the
    resource name (a string) as the first positional arg:

    - ``bucket = aws.s3.Bucket("my-bucket", website=site_cfg)``
        emits ``bucket -> site_cfg``.

    The same kwarg-reference rule applies: any kwarg whose value resolves
    to a previously assigned variable becomes an edge.

    Args:
        path: Path to a Pulumi Python file (typically ``__main__.py``).

    Returns:
        Deduped list of edges.
    """
    return _python_resource_graph(path, _looks_like_pulumi_call)


def _python_resource_graph(
    path: str,
    is_resource_call,
) -> list[tuple[str, str]]:
    """Shared helper for CDK / Pulumi Python parsing.

    Walks the AST collecting `var = <some_module>.<Class>(...)` assignments
    where the call shape matches `is_resource_call`. For each such call,
    every kwarg whose value is a Name/Attribute pointing to another
    construct variable becomes an edge `var -> referenced_var`.
    """
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)

    # Pass 1: collect variable names assigned from a "resource-shaped" call
    construct_vars: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not isinstance(node.value, ast.Call):
            continue
        if is_resource_call(node.value):
            construct_vars.add(target.id)

    # Pass 2: emit edges from each construct call's kwargs
    edges: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not is_resource_call(call):
            continue
        var_name = target.id
        for kw in call.keywords:
            if not kw.arg:
                continue
            refs = _construct_refs(kw.value, construct_vars)
            for ref in refs:
                if ref != var_name:
                    edges.append((var_name, ref))

    return _dedupe(edges)


def _construct_refs(expr: ast.expr, construct_vars: set[str]) -> list[str]:
    """Construct variables a kwarg value points at.

    ``bucket`` and ``bucket.id`` / ``group.id`` both refer to the variable
    the resource was assigned to. Lists of those are walked too.
    """
    if isinstance(expr, (ast.List, ast.Tuple)):
        found: list[str] = []
        for elt in expr.elts:
            found.extend(_construct_refs(elt, construct_vars))
        return found
    if isinstance(expr, ast.Name):
        return [expr.id] if expr.id in construct_vars else []
    if isinstance(expr, ast.Attribute):
        root: ast.expr = expr
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name) and root.id in construct_vars:
            return [root.id]
    return []


def _looks_like_cdk_call(call: ast.Call) -> bool:
    """Heuristic: AWS CDK constructs are called with `(scope, id, **kwargs)`.

    Match `Module.Class(self, "...", ...)` or `aws_xxx.Klass(scope, "...", ...)`
    where the second arg is a string (the construct id).
    """
    if not isinstance(call.func, ast.Attribute):
        return False
    if len(call.args) < 2:
        return False
    second = call.args[1]
    return isinstance(second, ast.Constant) and isinstance(second.value, str)


def _looks_like_pulumi_call(call: ast.Call) -> bool:
    """Heuristic: Pulumi resources are called with `("name", **kwargs)`.

    Match `Module.Class("name", ...)` or `aws.s3.Bucket("name", ...)` where
    the FIRST positional arg is a string literal.
    """
    if not isinstance(call.func, ast.Attribute):
        return False
    if not call.args:
        return False
    first = call.args[0]
    return isinstance(first, ast.Constant) and isinstance(first.value, str)


# ---------------------------------------------------------------------------
# OpenTelemetry traces (OTLP / Jaeger / Zipkin)
# ---------------------------------------------------------------------------

def from_otel_traces(path: str) -> list[tuple[str, str]]:
    """Extract service-level call edges from a trace export (JSON).

    Supports three formats — auto-detected by structure:

    - **OTLP JSON**: `{"resourceSpans": [{"scopeSpans": [{"spans": [...]}]}]}`
      (Default OpenTelemetry Collector / SDK export.)
    - **Jaeger**: `{"data": [{"spans": [...], "processes": {...}}]}`
      (`jaeger-query` HTTP API and `jaeger-cli`.)
    - **Zipkin**: `[{traceId, id, parentId, localEndpoint: {serviceName}}, ...]`
      (Zipkin v2 JSON API.)

    Edges are emitted at the **service** level, not the span level: a parent
    span owned by service A and a child span owned by service B produce a
    single edge ``A -> B``. Same-service spans (intra-process) are dropped,
    as are self-loops.

    Args:
        path: Path to the trace JSON file.

    Returns:
        Deduplicated list of ``(source_service, target_service)`` edges.

    Example::

        edges = se.extract.from_otel_traces("traces.json")
        result = se.encode(edges)
    """
    import json

    with open(path) as f:
        data = json.load(f)

    if isinstance(data, dict) and "resourceSpans" in data:
        return _dedupe(_otel_from_otlp(data))
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return _dedupe(_otel_from_jaeger(data))
    if isinstance(data, list) and data and isinstance(data[0], dict) and "traceId" in data[0]:
        return _dedupe(_otel_from_zipkin(data))

    raise ValueError(
        "Trace file format not recognized. Expected OTLP "
        "(`resourceSpans`), Jaeger (`data: [{spans, processes}]`), or "
        "Zipkin (top-level array with `traceId`/`localEndpoint`)."
    )


def _otel_from_otlp(data: dict) -> list[tuple[str, str]]:
    """Parse OTLP JSON: resourceSpans[*].scopeSpans[*].spans[*]."""
    span_to_service: dict[str, str] = {}
    parent_links: list[tuple[str, str]] = []  # (span_id, parent_span_id)

    for rs in data.get("resourceSpans", []):
        service = _otlp_service_name(rs.get("resource", {}))
        if not service:
            continue
        for ss in rs.get("scopeSpans", []) or rs.get("instrumentationLibrarySpans", []):
            for span in ss.get("spans", []):
                span_id = span.get("spanId") or span.get("span_id")
                parent_id = span.get("parentSpanId") or span.get("parent_span_id")
                if not span_id:
                    continue
                span_to_service[span_id] = service
                if parent_id and parent_id != "" and not _is_zero_id(parent_id):
                    parent_links.append((span_id, parent_id))

    edges: list[tuple[str, str]] = []
    for child_id, parent_id in parent_links:
        parent_svc = span_to_service.get(parent_id)
        child_svc = span_to_service.get(child_id)
        if parent_svc and child_svc and parent_svc != child_svc:
            edges.append((parent_svc, child_svc))
    return edges


def _otlp_service_name(resource: dict) -> str | None:
    """Extract `service.name` from an OTLP resource block."""
    for attr in resource.get("attributes", []):
        if attr.get("key") == "service.name":
            value = attr.get("value", {})
            for k in ("stringValue", "string_value"):
                if k in value:
                    return str(value[k])
    return None


def _is_zero_id(span_id: str) -> bool:
    """OTLP encodes 'no parent' as all-zeros hex/base64."""
    if not span_id:
        return True
    s = str(span_id).strip().rstrip("=")
    return all(c in "0A" for c in s) or s == "0"


def _otel_from_jaeger(data: dict) -> list[tuple[str, str]]:
    """Parse Jaeger JSON: data[*].spans[*] with processes lookup."""
    edges: list[tuple[str, str]] = []
    for trace in data.get("data", []):
        processes = trace.get("processes", {})
        span_to_service: dict[str, str] = {}
        for span in trace.get("spans", []):
            sid = span.get("spanID") or span.get("spanId")
            pid = span.get("processID") or span.get("processId")
            proc = processes.get(pid, {})
            svc = proc.get("serviceName")
            if sid and svc:
                span_to_service[sid] = svc
        for span in trace.get("spans", []):
            sid = span.get("spanID") or span.get("spanId")
            child_svc = span_to_service.get(sid)
            if not child_svc:
                continue
            # Jaeger represents parents via "references": [{refType: CHILD_OF, spanID}]
            for ref in span.get("references", []):
                if ref.get("refType") in ("CHILD_OF", "FOLLOWS_FROM"):
                    parent_id = ref.get("spanID") or ref.get("spanId")
                    parent_svc = span_to_service.get(parent_id)
                    if parent_svc and parent_svc != child_svc:
                        edges.append((parent_svc, child_svc))
    return edges


def _otel_from_zipkin(spans: list) -> list[tuple[str, str]]:
    """Parse Zipkin v2 JSON: flat list of {id, parentId, localEndpoint.serviceName}."""
    span_to_service: dict[str, str] = {}
    for span in spans:
        sid = span.get("id")
        endpoint = span.get("localEndpoint") or {}
        svc = endpoint.get("serviceName")
        if sid and svc:
            span_to_service[sid] = svc

    edges: list[tuple[str, str]] = []
    for span in spans:
        sid = span.get("id")
        pid = span.get("parentId")
        if not sid or not pid:
            continue
        parent_svc = span_to_service.get(pid)
        child_svc = span_to_service.get(sid)
        if parent_svc and child_svc and parent_svc != child_svc:
            edges.append((parent_svc, child_svc))
    return edges


# ---------------------------------------------------------------------------
# AI agent frameworks (LangGraph / CrewAI / AutoGen)
# ---------------------------------------------------------------------------
#
# All three parse Python source via `ast` only — they do NOT import the
# framework being analyzed. That means the SDK works on a repo without
# `pip install langgraph` etc.


def _ast_str_arg(node: ast.expr) -> str | None:
    """Resolve an AST node to a string label.

    Handles string constants, bare Name references (use the name),
    Attribute lookups (e.g. `agent.role` -> "agent.role"), and the
    LangGraph sentinels START / END.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        # `START` / `END` from langgraph come through as Name nodes;
        # any other Name is a Python variable we use as a node label.
        return node.id
    if isinstance(node, ast.Attribute):
        parts = []
        cur: ast.expr = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            return ".".join(reversed(parts))
    return None


def _kwargs(call: ast.Call) -> dict[str, ast.expr]:
    return {kw.arg: kw.value for kw in call.keywords if kw.arg}


def _called_name(fn: ast.expr) -> str | None:
    """Name or attribute of a call target: ``Task(...)`` or ``mod.Task(...)``."""
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return None


# LangGraph string sentinels. `__end__` / `__start__` are the runtime values
# of END / START; both forms show up in Command annotations.
_LG_SENTINELS = {"__end__": "END", "__start__": "START"}
_LG_BUILDERS = {"StateGraph", "MessageGraph"}
_LG_INVOKE_METHODS = {"invoke", "ainvoke", "stream", "astream"}


def _lg_norm(label: str | None) -> str | None:
    if label is None:
        return None
    return _LG_SENTINELS.get(label, label)


def _lg_targets(expr: ast.expr | None) -> list[str]:
    """Literal node names from a ``Command(goto=...)`` value.

    Accepts strings, ``START`` / ``END``, lists of those, conditional
    expressions, and ``Send("node", ...)``.
    """
    if expr is None:
        return []
    if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
        found: list[str] = []
        for elt in expr.elts:
            found.extend(_lg_targets(elt))
        return found
    if isinstance(expr, ast.IfExp):
        return _lg_targets(expr.body) + _lg_targets(expr.orelse)
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return [_LG_SENTINELS.get(expr.value, expr.value)]
    if isinstance(expr, ast.Name) and expr.id in ("END", "START"):
        return [expr.id]
    if isinstance(expr, ast.Attribute) and expr.attr in ("END", "START"):
        return [expr.attr]
    if isinstance(expr, ast.Call) and _called_name(expr.func) == "Send" and expr.args:
        return _lg_targets(expr.args[0])
    return []


def _lg_annotation_targets(ann: ast.expr | None) -> list[str]:
    """Targets from ``-> Command[Literal["a", "b"]]`` (unions unwrapped)."""
    if ann is None:
        return []
    if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
        return _lg_annotation_targets(ann.left) + _lg_annotation_targets(ann.right)
    if not isinstance(ann, ast.Subscript):
        return []
    if _called_name(ann.value) != "Command":
        return []
    sl = ann.slice
    if isinstance(sl, ast.Subscript) and _called_name(sl.value) == "Literal":
        return _lg_targets(sl.slice)
    return _lg_targets(sl)


def _lg_owner(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id
    return None


def _lg_invoked_builder(call: ast.Call, compiled: dict[str, str]) -> str | None:
    """Builder name when ``call`` runs a compiled graph (``graph.ainvoke(...)``)."""
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr not in _LG_INVOKE_METHODS:
        return None
    target = func.value
    if isinstance(target, ast.Name):
        return compiled.get(target.id)
    if (
        isinstance(target, ast.Call)
        and isinstance(target.func, ast.Attribute)
        and target.func.attr == "compile"
        and isinstance(target.func.value, ast.Name)
    ):
        return target.func.value.id
    return None


def _lg_added_node(call: ast.Call) -> tuple[str, ast.expr] | None:
    """``(node_name, action)`` from ``add_node``, or None if it isn't static."""
    kw = _kwargs(call)
    if call.args:
        first: ast.expr | None = call.args[0]
        action = call.args[1] if len(call.args) > 1 else kw.get("action")
    else:
        first = kw.get("node")
        action = kw.get("action")
    if isinstance(first, ast.Constant) and isinstance(first.value, str) and action is not None:
        return first.value, action
    # add_node(fn) uses the function's name as the node name.
    if isinstance(first, ast.Name) and action is None:
        return first.id, first
    return None


def _lg_top_builder(
    builders: list[str],
    mounted: dict[str, tuple[str | None, str]],
    invoked: set[str],
) -> str | None:
    """Which builder keeps bare ``START`` / ``END``.

    A builder compiled into a node of another graph, or invoked from a node
    function, is a subgraph: its sentinels are not the file's START/END.
    Among the remaining builders, one that mounts other graphs is the parent.
    With several unrelated graphs, the last one defined keeps the bare labels
    (the usual "helpers first, app last" layout).
    """
    def pick(cands: list[str]) -> str | None:
        if not cands:
            return None
        parents = [b for b in cands if any(owner == b for owner, _node in mounted.values())]
        if parents:
            return parents[-1]
        return cands[-1]

    top = pick([b for b in builders if b not in mounted and b not in invoked])
    if top is not None:
        return top
    return pick([b for b in builders if b not in mounted])


def from_langgraph(path: str) -> list[tuple[str, str]]:
    """Extract edges from a LangGraph workflow definition.

    Recognized patterns (the receiver of ``add_edge`` does not matter; the
    method name does):

    - ``g.add_edge("planner", "researcher")`` / ``g.add_edge(START, "planner")``
    - ``g.add_conditional_edges("planner", router, {"yes": "act", "no": END})``
    - ``g.set_entry_point("planner")`` / ``g.set_finish_point("act")``
    - ``Command(goto="next")``, ``Command(goto=[...])``, ``Command(goto=Send("n"))``,
      and ``-> Command[Literal["a", "b"]]`` on a function passed to ``add_node``
    - ``compiled.ainvoke(...)`` / ``invoke`` / ``stream`` / ``astream`` inside a
      node function: an edge from that node to the compiled graph's entry

    Several ``StateGraph`` builders in one file keep separate ``START`` / ``END``.
    A builder compiled and mounted (``parent.add_node("x", sub.compile())``)
    wires its entry and exit through ``x``. An extra builder that is not the
    top-level graph uses ``START[<builder>]`` / ``END[<builder>]``.

    Args:
        path: Path to a Python file defining the graph.

    Returns:
        Deduped list of ``(source, target)`` edges.
    """
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)

    # Pass 1: builders (`x = StateGraph(...)`) and `y = x.compile()` aliases.
    # Collected first so a compile that appears below add_node still mounts.
    builders: list[str] = []
    seen_builders: set[str] = set()
    compiled: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not isinstance(node.value, ast.Call):
            continue
        fname = _called_name(node.value.func)
        if fname in _LG_BUILDERS:
            if target.id not in seen_builders:
                builders.append(target.id)
                seen_builders.add(target.id)
        elif (
            fname == "compile"
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
        ):
            compiled[target.id] = node.value.func.value.id

    # Pass 2: edges declared on a builder, plus node -> function / subgraph.
    # raw entries are (builder variable or None, source, target).
    raw: list[tuple[str | None, str, str]] = []
    func_to_nodes: dict[str, list[tuple[str | None, str]]] = {}
    mounted: dict[str, tuple[str | None, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr
        owner = _lg_owner(node)

        if method == "add_edge" and len(node.args) >= 2:
            src = _lg_norm(_ast_str_arg(node.args[0]))
            dst = _lg_norm(_ast_str_arg(node.args[1]))
            if src and dst:
                raw.append((owner, src, dst))

        elif method == "add_conditional_edges":
            if not node.args:
                continue
            src = _lg_norm(_ast_str_arg(node.args[0]))
            if not src:
                continue
            if len(node.args) >= 3:
                mapping_node: ast.expr | None = node.args[2]
            else:
                kw = _kwargs(node)
                mapping_node = kw.get("path_map") or kw.get("conditional_edge_mapping")
            if isinstance(mapping_node, ast.Dict):
                for value in mapping_node.values:
                    dst = _lg_norm(_ast_str_arg(value))
                    if dst:
                        raw.append((owner, src, dst))
            elif isinstance(mapping_node, (ast.List, ast.Tuple)):
                for dst in _lg_targets(mapping_node):
                    raw.append((owner, src, dst))

        elif method == "set_entry_point" and node.args:
            dst = _lg_norm(_ast_str_arg(node.args[0]))
            if dst:
                raw.append((owner, "START", dst))

        elif method == "set_finish_point" and node.args:
            src = _lg_norm(_ast_str_arg(node.args[0]))
            if src:
                raw.append((owner, src, "END"))

        elif method == "add_node":
            added = _lg_added_node(node)
            if added is None:
                continue
            node_name, action = added
            if isinstance(action, ast.Name):
                func_to_nodes.setdefault(action.id, []).append((owner, node_name))
                sub = compiled.get(action.id)
                if sub:
                    mounted[sub] = (owner, node_name)
            elif (
                isinstance(action, ast.Call)
                and isinstance(action.func, ast.Attribute)
                and action.func.attr == "compile"
                and isinstance(action.func.value, ast.Name)
            ):
                mounted[action.func.value.id] = (owner, node_name)

    entries: dict[str, list[str]] = {}
    for owner, src, dst in raw:
        if src == "START" and owner and dst not in ("START", "END"):
            bucket = entries.setdefault(owner, [])
            if dst not in bucket:
                bucket.append(dst)

    # Pass 3: Command routing and imperative subgraph calls inside node functions.
    invoked: set[str] = set()
    for fdef in ast.walk(tree):
        if not isinstance(fdef, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        bindings = func_to_nodes.get(fdef.name)
        if not bindings:
            continue
        targets = list(_lg_annotation_targets(fdef.returns))
        invoked_here: list[str] = []
        for call in ast.walk(fdef):
            if not isinstance(call, ast.Call):
                continue
            if _called_name(call.func) == "Command":
                targets.extend(_lg_targets(_kwargs(call).get("goto")))
            builder_name = _lg_invoked_builder(call, compiled)
            if builder_name:
                invoked_here.append(builder_name)
        # A node that runs its own graph is not a subgraph call. Only a
        # different builder is demoted so it cannot take the bare START/END.
        caller_owners = {owner for owner, _name in bindings}
        for builder_name in invoked_here:
            if any(owner is not None and owner != builder_name for owner in caller_owners):
                invoked.add(builder_name)
        for graph_owner, node_name in bindings:
            for dst in targets:
                raw.append((graph_owner, node_name, dst))
            for builder_name in invoked_here:
                for entry in entries.get(builder_name, []):
                    raw.append((graph_owner, node_name, entry))

    top = _lg_top_builder(builders, mounted, invoked)
    builder_set = set(builders)

    def _resolve(owner: str | None, label: str) -> str:
        if label not in ("START", "END"):
            return label
        if owner in mounted:
            return mounted[owner][1]
        if owner in builder_set and owner != top:
            return f"{label}[{owner}]"
        return label

    edges = [(_resolve(owner, src), _resolve(owner, dst)) for owner, src, dst in raw]
    return _dedupe(edges)


def from_crewai(path: str) -> list[tuple[str, str]]:
    """Extract edges from a CrewAI script.

    Patterns:

    - ``my_task = Task(description=..., agent=researcher)``
        emits ``researcher -> my_task``
    - ``my_task = Task(..., context=[prep_task, lookup_task])``
        emits ``prep_task -> my_task`` and ``lookup_task -> my_task``
    - ``Crew(agents=[a, b], tasks=[t1, t2], manager_agent=mgr)``
        emits ``mgr -> a``, ``mgr -> b`` (manager broadcasts)
    - ``@CrewBase`` classes (``@agent`` / ``@task`` / ``@crew``): each task
        method's ``Task(agent=self.agent())`` emits ``agent -> task``.
        ``Process.sequential`` (the default) chains tasks in class-body
        order. ``Process.hierarchical`` with ``manager_agent=self.mgr()``
        emits ``mgr -> agent``. ``context:`` in ``tasks.yaml`` and
        ``context=[self.other()]`` add dependency edges. A method defined
        twice keeps the first class-dict slot and the last body, matching
        Python and CrewBase.

    Args:
        path: Path to a Python file using crewai.

    Returns:
        Deduped list of edges. Node names are Python variable or method names
        from the source file.
    """
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)

    edges: list[tuple[str, str]] = []

    def _is_named_call(call: ast.Call, name: str) -> bool:
        f = call.func
        if isinstance(f, ast.Name) and f.id == name:
            return True
        if isinstance(f, ast.Attribute) and f.attr == name:
            return True
        return False

    for node in ast.walk(tree):
        # Find `task_var = Task(...)` or `task_var = SomeTask(...)`
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                call = node.value
                task_name = target.id
                if _is_named_call(call, "Task"):
                    kwargs = _kwargs(call)
                    if "agent" in kwargs:
                        agent = _ast_str_arg(kwargs["agent"])
                        if agent:
                            edges.append((agent, task_name))
                    if "context" in kwargs and isinstance(kwargs["context"], (ast.List, ast.Tuple)):
                        for ctx in kwargs["context"].elts:
                            ctx_name = _ast_str_arg(ctx)
                            if ctx_name:
                                edges.append((ctx_name, task_name))

        # Find `Crew(agents=[a, b], manager_agent=mgr)` (manager fans out to agents)
        if isinstance(node, ast.Call) and _is_named_call(node, "Crew"):
            kwargs = _kwargs(node)
            agents_list: list[str] = []
            if "agents" in kwargs and isinstance(kwargs["agents"], (ast.List, ast.Tuple)):
                for a in kwargs["agents"].elts:
                    name = _ast_str_arg(a)
                    if name:
                        agents_list.append(name)
            manager = None
            if "manager_agent" in kwargs:
                manager = _ast_str_arg(kwargs["manager_agent"])
            if manager:
                for a in agents_list:
                    if a != manager:
                        edges.append((manager, a))

    edges.extend(_crewai_decorator_edges(tree, path))
    return _dedupe(edges)


def _decorator_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for dec in getattr(node, "decorator_list", []):
        cur = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(cur, ast.Name):
            names.add(cur.id)
        elif isinstance(cur, ast.Attribute):
            names.add(cur.attr)
    return names


def _imports_crewai(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".", 1)[0] == "crewai" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.split(".", 1)[0] == "crewai":
                return True
    return False


def _crew_ref(expr: ast.expr | None) -> str | None:
    """``self.agent()``, ``self.agent``, or a bare name -> that name."""
    if isinstance(expr, ast.Call):
        expr = expr.func
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name) and expr.value.id == "self":
        return expr.attr
    if isinstance(expr, ast.Name):
        return expr.id
    return None


def _class_str_attr(cls: ast.ClassDef, attr: str) -> str | None:
    for stmt in cls.body:
        target_name = None
        value = None
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            target_name = stmt.targets[0].id
            value = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            target_name = stmt.target.id
            value = stmt.value
        if target_name == attr and isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None


def _subscript_str(node: ast.expr) -> str | None:
    sl = node.slice if isinstance(node, ast.Subscript) else None
    if sl is None:
        return None
    # Python 3.8 wrapped the index in ast.Index. 3.9+ does not.
    if type(sl).__name__ == "Index":
        sl = getattr(sl, "value", None)
    if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
        return sl.value
    return None


def _crewai_decorator_edges(tree: ast.AST, path: str) -> list[tuple[str, str]]:
    """Edges for ``@CrewBase`` crews (``crewai create crew``).

    A class is a decorator crew when it carries ``@CrewBase`` or the file
    imports crewai. A Celery ``@task`` in an unrelated file is left alone.
    """
    edges: list[tuple[str, str]] = []
    file_imports = _imports_crewai(tree)

    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        decos = _decorator_names(cls)
        if "CrewBase" not in decos and not file_imports:
            continue
        methods = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        task_methods = [m for m in methods if "task" in _decorator_names(m)]
        agent_methods = [m.name for m in methods if "agent" in _decorator_names(m)]
        if not task_methods and not agent_methods:
            continue

        # Class dict keeps the first insertion slot and the last function body.
        order: list[str] = []
        last_def: dict[str, ast.AST] = {}
        for method in task_methods:
            if method.name not in last_def:
                order.append(method.name)
            last_def[method.name] = method

        inline_agent: dict[str, str] = {}
        yaml_key_to_method: dict[str, str] = {}
        for name in order:
            method = last_def[name]
            for call in ast.walk(method):
                if not isinstance(call, ast.Call) or _called_name(call.func) != "Task":
                    continue
                kw = _kwargs(call)
                agent = _crew_ref(kw.get("agent"))
                if agent:
                    inline_agent[name] = agent
                    edges.append((agent, name))
                ctx = kw.get("context")
                if isinstance(ctx, (ast.List, ast.Tuple)):
                    for item in ctx.elts:
                        ctx_name = _crew_ref(item)
                        if ctx_name:
                            edges.append((ctx_name, name))
                cfg = kw.get("config")
                if isinstance(cfg, ast.Subscript):
                    key = _subscript_str(cfg)
                    if key:
                        yaml_key_to_method[key] = name

        rel = _class_str_attr(cls, "tasks_config") or os.path.join("config", "tasks.yaml")
        yaml_path = rel if os.path.isabs(rel) else os.path.join(os.path.dirname(os.path.abspath(path)), rel)
        if os.path.isfile(yaml_path):
            try:
                data = _load_single_yaml(yaml_path) or {}
            except Exception:
                # A missing PyYAML install or a broken tasks.yaml should not
                # drop the agent/task edges already parsed from the class.
                data = {}
            if isinstance(data, dict):
                agent_set = set(agent_methods)
                for key, spec in data.items():
                    if not isinstance(key, str) or not isinstance(spec, dict):
                        continue
                    task_name = yaml_key_to_method.get(key, key)
                    if task_name not in last_def:
                        continue
                    if task_name not in inline_agent:
                        agent_name = spec.get("agent")
                        if isinstance(agent_name, str) and agent_name in agent_set:
                            edges.append((agent_name, task_name))
                    ctx = spec.get("context") or []
                    if isinstance(ctx, str):
                        ctx = [ctx]
                    if isinstance(ctx, list):
                        for item in ctx:
                            if not isinstance(item, str):
                                continue
                            # CrewBase resolves context entries as task method
                            # names. A yaml key that the method loads via
                            # tasks_config["key"] is accepted too.
                            edges.append((yaml_key_to_method.get(item, item), task_name))

        process = "sequential"
        manager: str | None = None
        for method in methods:
            if "crew" not in _decorator_names(method):
                continue
            for call in ast.walk(method):
                if not isinstance(call, ast.Call) or _called_name(call.func) != "Crew":
                    continue
                kw = _kwargs(call)
                process = "sequential"
                proc = kw.get("process")
                if isinstance(proc, ast.Call):
                    proc = proc.func
                if isinstance(proc, ast.Attribute):
                    process = proc.attr
                elif isinstance(proc, ast.Constant) and isinstance(proc.value, str):
                    process = proc.value
                manager = _crew_ref(kw.get("manager_agent"))
        # manager_agent fans out even if the process name is omitted; the
        # process value only decides whether tasks form a sequential chain.
        if manager:
            for agent in agent_methods:
                if agent != manager:
                    edges.append((manager, agent))
        if process == "sequential":
            for left, right in zip(order, order[1:]):
                edges.append((left, right))
    return edges


def from_autogen(path: str) -> list[tuple[str, str]]:
    """Extract edges from a Microsoft AutoGen / AG2 / autogen-agentchat script.

    Patterns recognized:

    **Legacy AutoGen (autogen-core 0.2.x style):**

    - ``GroupChat(agents=[a, b, c])`` (no explicit manager) → fully connected
    - ``GroupChat(agents=[...])`` + ``GroupChatManager(groupchat=gc)`` → star (manager -> agents)
    - ``user_proxy.initiate_chat(assistant, ...)`` → ``user_proxy -> assistant``

    **Modern AutoGen (autogen-agentchat 0.4+):**

    - ``RoundRobinGroupChat([a, b, c])`` → round-robin chain (a -> b -> c -> a)
    - ``SelectorGroupChat([a, b, c], ...)`` → fully connected (selector picks any)
    - ``Swarm([a, b, c], ...)`` → fully connected
    - ``team.run(task=...)`` / ``team.run_stream(...)`` recognized but emit no edges

    Args:
        path: Path to a Python file using autogen / autogen-agentchat / ag2.

    Returns:
        Deduped list of edges. Node names are Python variable names.
    """
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)

    edges: list[tuple[str, str]] = []

    def _name_or_attr(call: ast.Call, names: set[str]) -> bool:
        f = call.func
        if isinstance(f, ast.Name):
            return f.id in names
        if isinstance(f, ast.Attribute):
            return f.attr in names
        return False

    def _agents_list(call: ast.Call) -> list[str]:
        """Pull the agents list — either positional first arg or `agents=` kwarg."""
        node = None
        if call.args and isinstance(call.args[0], (ast.List, ast.Tuple)):
            node = call.args[0]
        else:
            node = _kwargs(call).get("agents") or _kwargs(call).get("participants")
        if not isinstance(node, (ast.List, ast.Tuple)):
            return []
        return [n for n in (_ast_str_arg(a) for a in node.elts) if n]

    # First pass: collect every group-chat-style construct's agents list.
    # Each entry: (var_name, agents, kind) where kind in
    # {"legacy", "round_robin", "selector", "swarm"}.
    groupchats: dict[str, tuple[list[str], str]] = {}
    LEGACY = {"GroupChat"}
    ROUND_ROBIN = {"RoundRobinGroupChat"}
    SELECTOR = {"SelectorGroupChat", "MagenticOneGroupChat"}
    SWARM = {"Swarm"}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if _name_or_attr(call, LEGACY):
            agents = _agents_list(call)
            if agents:
                groupchats[target.id] = (agents, "legacy")
        elif _name_or_attr(call, ROUND_ROBIN):
            agents = _agents_list(call)
            if agents:
                groupchats[target.id] = (agents, "round_robin")
        elif _name_or_attr(call, SELECTOR):
            agents = _agents_list(call)
            if agents:
                groupchats[target.id] = (agents, "selector")
        elif _name_or_attr(call, SWARM):
            agents = _agents_list(call)
            if agents:
                groupchats[target.id] = (agents, "swarm")

    # Pass 2: legacy GroupChatManager → star pattern
    chat_to_manager: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not _name_or_attr(call, {"GroupChatManager"}):
            continue
        kw = _kwargs(call)
        gc_node = kw.get("groupchat") or kw.get("group_chat")
        gc_name = _ast_str_arg(gc_node) if gc_node else None
        if gc_name and gc_name in groupchats:
            chat_to_manager[gc_name] = target.id

    # Emit edges based on chat kind
    for chat, (agents, kind) in groupchats.items():
        if kind == "legacy":
            manager = chat_to_manager.get(chat)
            if manager:
                for a in agents:
                    if a != manager:
                        edges.append((manager, a))
            else:
                for a in agents:
                    for b in agents:
                        if a != b:
                            edges.append((a, b))
        elif kind == "round_robin":
            # Round-robin: each agent addresses the next; last wraps to first.
            for i in range(len(agents)):
                edges.append((agents[i], agents[(i + 1) % len(agents)]))
        elif kind in ("selector", "swarm"):
            # Fully connected — selector or swarm can route between any pair.
            for a in agents:
                for b in agents:
                    if a != b:
                        edges.append((a, b))

    # Second pass: `x.initiate_chat(y, ...)` -> x -> y
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "initiate_chat":
            continue
        caller = _ast_str_arg(node.func.value)
        if not caller or not node.args:
            continue
        recipient = _ast_str_arg(node.args[0])
        if recipient:
            edges.append((caller, recipient))

    return _dedupe(edges)


# ---------------------------------------------------------------------------
# Auto-detect
# ---------------------------------------------------------------------------

def _source_label_set(
    value: set[str] | list[str] | tuple[str, ...] | str | None,
) -> set[str] | None:
    """Normalize an include/exclude argument. A bare string is one label."""
    if value is None:
        return None
    if isinstance(value, str):
        return {value}
    return {str(item) for item in value}


def from_directory(
    path: str = ".",
    *,
    include: set[str] | list[str] | tuple[str, ...] | str | None = None,
    exclude: set[str] | list[str] | tuple[str, ...] | str | None = None,
) -> tuple[list[tuple[str, str]], dict[str, int]]:
    """Scan a directory and extract edges from all recognized infrastructure files.

    Auto-detects docker-compose, Kubernetes manifests, GitHub Actions
    workflows, Terraform, Python imports, and the other parsers below.

    Args:
        path: Directory to scan (default: current directory).
        include: If given, only these source labels are parsed. A string is
            one label, not a sequence of characters.
        exclude: Source labels to skip. Applied after ``include``. Omit both
            to preserve the historical "parse everything recognized" behavior.

    Source labels: ``docker-compose``, ``kubernetes``, ``github-actions``,
    ``terraform``, ``python-imports``, ``package-json``, ``otel-traces``,
    ``langgraph``, ``crewai``, ``autogen``, ``aws-cdk``, ``pulumi``,
    ``cloudformation``.

    Returns:
        Tuple of (edges, sources) where sources maps format name to edge count.

    Example::

        edges, sources = se.extract.from_directory(".")
        edges, sources = se.extract.from_directory(
            ".", exclude={"github-actions", "python-imports"}
        )
        print(f"Found {len(edges)} edges from {sources}")
        result = se.encode(edges)
        print(result.table)
    """
    all_edges: list[tuple[str, str]] = []
    sources: dict[str, int] = {}
    included = _source_label_set(include)
    excluded = _source_label_set(exclude) or set()

    def _want(label: str) -> bool:
        if included is not None and label not in included:
            return False
        return label not in excluded

    # Docker Compose
    for name in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
        compose_path = os.path.join(path, name)
        if os.path.isfile(compose_path) and _want("docker-compose"):
            try:
                edges = from_docker_compose(compose_path)
                if edges:
                    all_edges.extend(edges)
                    sources["docker-compose"] = len(edges)
            except Exception:
                pass

    # Kubernetes — find any directory containing YAML that declares a k8s
    # resource (`apiVersion` + `kind`), rather than trusting conventional dir
    # names. This catches manifests in non-standard locations (e.g. release/,
    # kubernetes-manifests/). Running once per directory keeps cross-file
    # Service->Deployment selector matching intact.
    k8s_dirs_found: set[str] = set()
    if _want("kubernetes"):
        for ext in ("**/*.yaml", "**/*.yml"):
            for fp in glob.glob(os.path.join(path, ext), recursive=True):
                if any(p in fp for p in ("node_modules", ".venv", "venv", ".git")):
                    continue
                try:
                    head = open(fp, encoding="utf-8", errors="replace").read(2048)
                except OSError:
                    continue
                if "apiVersion:" in head and "kind:" in head:
                    k8s_dirs_found.add(os.path.dirname(fp) or path)
    for d in sorted(k8s_dirs_found):
        try:
            edges = from_kubernetes(d)
            if edges:
                all_edges.extend(edges)
                sources["kubernetes"] = sources.get("kubernetes", 0) + len(edges)
        except Exception:
            pass

    # GitHub Actions
    gh_path = os.path.join(path, ".github", "workflows")
    if os.path.isdir(gh_path) and _want("github-actions"):
        try:
            edges = from_github_actions(gh_path)
            if edges:
                all_edges.extend(edges)
                sources["github-actions"] = len(edges)
        except Exception:
            pass

    # Terraform
    tf_files = glob.glob(os.path.join(path, "**/*.tf"), recursive=True) if _want("terraform") else []
    if tf_files:
        try:
            edges = from_terraform(path)
            if edges:
                all_edges.extend(edges)
                sources["terraform"] = len(edges)
        except Exception:
            pass

    # Python imports
    py_files = glob.glob(os.path.join(path, "**/*.py"), recursive=True) if _want("python-imports") else []
    # Filter out venv/node_modules/hidden dirs
    py_files = [f for f in py_files if not any(
        p in f for p in ["node_modules", ".venv", "venv", "__pycache__", ".git"]
    )]
    if py_files:
        try:
            edges = from_python_imports(path)
            if edges:
                all_edges.extend(edges)
                sources["python-imports"] = len(edges)
        except Exception:
            pass

    # package.json (monorepo workspaces)
    root_pkg = os.path.join(path, "package.json")
    if os.path.isfile(root_pkg) and _want("package-json"):
        try:
            edges = from_package_json_workspaces(path)
            if edges:
                all_edges.extend(edges)
                sources["package-json"] = len(edges)
        except Exception:
            pass

    # OpenTelemetry traces — covers the highest-quality edge source (real
    # runtime calls). Auto-picked up from common filenames at the root.
    for name in ["traces.json", "otel.json", "otlp.json", "jaeger.json", "zipkin.json"]:
        trace_path = os.path.join(path, name)
        if os.path.isfile(trace_path) and _want("otel-traces"):
            try:
                edges = from_otel_traces(trace_path)
                if edges:
                    all_edges.extend(edges)
                    sources["otel-traces"] = sources.get("otel-traces", 0) + len(edges)
            except Exception:
                pass
    # Also try a `traces/` directory containing one or more trace files
    traces_dir = os.path.join(path, "traces")
    if os.path.isdir(traces_dir) and _want("otel-traces"):
        for fname in glob.glob(os.path.join(traces_dir, "*.json")):
            try:
                edges = from_otel_traces(fname)
                if edges:
                    all_edges.extend(edges)
                    sources["otel-traces"] = sources.get("otel-traces", 0) + len(edges)
            except Exception:
                pass

    # AI agent frameworks + AWS CDK + Pulumi — for each file that imports a
    # known framework, run the matching parser on JUST that file (cheaper +
    # more accurate than walking every Python file).
    py_specs = (
        ("langgraph",   ("langgraph",),                          from_langgraph),
        ("crewai",      ("crewai",),                             from_crewai),
        ("autogen",     ("autogen", "autogen_agentchat", "autogen_core", "autogen_ext", "ag2"), from_autogen),
        ("aws-cdk",     ("aws_cdk", "aws_cdk_lib"),              from_aws_cdk),
        ("pulumi",      ("pulumi",),                             from_pulumi),
    )
    py_files = []
    if any(_want(label) for label, _prefixes, _parser in py_specs):
        py_files = glob.glob(os.path.join(path, "**/*.py"), recursive=True)
        py_files = [f for f in py_files if not any(
            p in f for p in ["node_modules", ".venv", "venv", "__pycache__", ".git"]
        )]
    for fpath in py_files:
        try:
            head = open(fpath, encoding="utf-8", errors="replace").read(4096)
        except OSError:
            continue
        for label, prefixes, parser in py_specs:
            if not _want(label):
                continue
            if not any(f"import {p}" in head or f"from {p}" in head for p in prefixes):
                continue
            try:
                edges = parser(fpath)
                if edges:
                    all_edges.extend(edges)
                    sources[label] = sources.get(label, 0) + len(edges)
            except Exception:
                pass

    # CloudFormation — pick up *.yaml / *.yml at root or under cloudformation/
    # / templates/. Detection is cheap (the file must contain "Resources:" near
    # the top to be considered).
    cfn_dirs = [path] + [
        os.path.join(path, d) for d in ("cloudformation", "templates", "cfn")
        if os.path.isdir(os.path.join(path, d))
    ]
    seen_cfn: set[str] = set()
    if not _want("cloudformation"):
        cfn_dirs = []
    for d in cfn_dirs:
        if not os.path.isdir(d):
            continue
        for ext in ("*.yaml", "*.yml", "*.json", "*.template"):
            for fp in glob.glob(os.path.join(d, ext)):
                if fp in seen_cfn:
                    continue
                seen_cfn.add(fp)
                try:
                    with open(fp, encoding="utf-8", errors="replace") as fh:
                        head = fh.read(2048)
                except OSError:
                    continue
                # Cheap heuristic to skip non-CFN YAML/JSON
                if "AWSTemplateFormatVersion" not in head and '"Resources"' not in head and "\nResources:" not in head:
                    continue
                try:
                    edges = from_cloudformation(fp)
                    if edges:
                        all_edges.extend(edges)
                        sources["cloudformation"] = sources.get("cloudformation", 0) + len(edges)
                except Exception:
                    pass

    return _dedupe(all_edges), sources


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dedupe(edges: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Remove duplicate edges and self-loops, preserve order."""
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for src, dst in edges:
        if src != dst and (src, dst) not in seen:
            seen.add((src, dst))
            result.append((src, dst))
    return result
