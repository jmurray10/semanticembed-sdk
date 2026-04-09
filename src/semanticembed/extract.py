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
    label selectors, service references, and ingress backends.

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
                edges.append((svc_name, dep_name))

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
                    edges.append((ing_name, svc_ref))

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
                            edges.append((dep_name, svc_name))

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

    Returns:
        List of (source, target) edge tuples.

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
    ref_pattern = re.compile(r"(\w+\.\w+)\.")

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
            # Short label: use resource name, prefix with type if ambiguous
            resources[full_name] = res_name

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

def from_python_imports(path: str = ".") -> list[tuple[str, str]]:
    """Extract module dependency edges from Python import statements.

    Scans ``.py`` files and builds a directed graph of which modules import
    which. Only includes edges between modules that exist in the scanned
    directory (ignores stdlib and third-party imports).

    Args:
        path: Path to a Python file or directory of Python files.

    Returns:
        List of (importer, imported) edge tuples using module names.

    Example::

        edges = se.extract.from_python_imports("src/")
        result = se.encode(edges)
        print(result.table)
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

    import_re = re.compile(
        r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE
    )

    edges: list[tuple[str, str]] = []
    for f, src_mod in file_to_module.items():
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except Exception:
            continue

        for match in import_re.finditer(content):
            imported = match.group(1) or match.group(2)
            if not imported:
                continue
            # Check if the imported module is local
            # Try the full name, then progressively shorter prefixes.
            # Also try stripping the first component (handles `from myapp.models.user`
            # when scanning inside the `myapp/` directory where modules are `models.user`).
            target = None
            parts = imported.split(".")
            candidates = [parts]
            if len(parts) > 1:
                candidates.append(parts[1:])  # stripped first component
            for candidate_parts in candidates:
                for i in range(len(candidate_parts), 0, -1):
                    candidate = ".".join(candidate_parts[:i])
                    if candidate in local_modules and candidate != src_mod:
                        target = candidate
                        break
                if target:
                    break
            if target:
                # Use short names (last component) for readability
                src_short = src_mod.split(".")[-1]
                dst_short = target.split(".")[-1]
                # If short names collide, use longer qualified names
                if src_short == dst_short:
                    src_short = src_mod
                    dst_short = target
                edges.append((src_short, dst_short))

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
# Auto-detect
# ---------------------------------------------------------------------------

def from_directory(path: str = ".") -> tuple[list[tuple[str, str]], dict[str, int]]:
    """Scan a directory and extract edges from all recognized infrastructure files.

    Auto-detects docker-compose, Kubernetes manifests, GitHub Actions
    workflows, and Terraform files.

    Args:
        path: Directory to scan (default: current directory).

    Returns:
        Tuple of (edges, sources) where sources maps format name to edge count.

    Example::

        edges, sources = se.extract.from_directory(".")
        print(f"Found {len(edges)} edges from {sources}")
        result = se.encode(edges)
        print(result.table)
    """
    all_edges: list[tuple[str, str]] = []
    sources: dict[str, int] = {}

    # Docker Compose
    for name in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
        compose_path = os.path.join(path, name)
        if os.path.isfile(compose_path):
            try:
                edges = from_docker_compose(compose_path)
                if edges:
                    all_edges.extend(edges)
                    sources["docker-compose"] = len(edges)
            except Exception:
                pass

    # Kubernetes
    k8s_dirs = ["k8s", "kubernetes", "manifests", "deploy", "deployments"]
    for d in k8s_dirs:
        k8s_path = os.path.join(path, d)
        if os.path.isdir(k8s_path):
            try:
                edges = from_kubernetes(k8s_path)
                if edges:
                    all_edges.extend(edges)
                    sources["kubernetes"] = sources.get("kubernetes", 0) + len(edges)
            except Exception:
                pass

    # GitHub Actions
    gh_path = os.path.join(path, ".github", "workflows")
    if os.path.isdir(gh_path):
        try:
            edges = from_github_actions(gh_path)
            if edges:
                all_edges.extend(edges)
                sources["github-actions"] = len(edges)
        except Exception:
            pass

    # Terraform
    tf_files = glob.glob(os.path.join(path, "**/*.tf"), recursive=True)
    if tf_files:
        try:
            edges = from_terraform(path)
            if edges:
                all_edges.extend(edges)
                sources["terraform"] = len(edges)
        except Exception:
            pass

    # Python imports
    py_files = glob.glob(os.path.join(path, "**/*.py"), recursive=True)
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
    if os.path.isfile(root_pkg):
        try:
            edges = from_package_json_workspaces(path)
            if edges:
                all_edges.extend(edges)
                sources["package-json"] = len(edges)
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
