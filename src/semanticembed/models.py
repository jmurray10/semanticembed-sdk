"""Response models for SemanticEmbed SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DIMENSION_NAMES = ["depth", "independence", "hierarchy", "throughput", "criticality", "fanout"]


@dataclass
class RiskEntry:
    """A single structural risk finding."""

    node: str
    category: str
    severity: str
    description: str
    value: float

    def json(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "value": self.value,
        }


@dataclass
class RiskReport:
    """Structural risk report for a graph."""

    risks: list[RiskEntry] = field(default_factory=list)

    def by_category(self, category: str) -> list[RiskEntry]:
        """Filter risks by category name (case-insensitive)."""
        cat = category.lower().replace("_", " ").replace("-", " ")
        return [r for r in self.risks if cat in r.category.lower().replace("_", " ")]

    def by_severity(self, severity: str) -> list[RiskEntry]:
        """Filter risks by severity level."""
        return [r for r in self.risks if r.severity == severity]

    def json(self) -> list[dict[str, Any]]:
        return [r.json() for r in self.risks]

    def __str__(self) -> str:
        if not self.risks:
            return "STRUCTURAL RISK REPORT\n======================\n\nNo structural risks detected."

        lines = ["STRUCTURAL RISK REPORT", "=" * 22, ""]

        # Group by category
        categories: dict[str, list[RiskEntry]] = {}
        for r in self.risks:
            categories.setdefault(r.category, []).append(r)

        for cat, entries in categories.items():
            label = cat.upper().replace("_", " ")
            lines.append(f"{label}:")
            for r in entries:
                lines.append(f"  - {r.node:<30} | {r.description}")
            lines.append("")

        # Actionable summary
        n_critical = len([r for r in self.risks if r.severity == "critical"])
        n_warning = len([r for r in self.risks if r.severity == "warning"])
        n_info = len([r for r in self.risks if r.severity == "info"])

        lines.append("WHAT TO DO")
        lines.append("-" * 10)

        actions = _suggest_actions(categories)
        for action in actions:
            lines.append(f"  {action}")
        lines.append("")

        lines.append(f"Total: {len(self.risks)} risks "
                      f"({n_critical} critical, {n_warning} warning, {n_info} info)")

        return "\n".join(lines)


# Action suggestions per risk category
_ACTION_MAP = {
    "SINGLE_POINT_OF_FAILURE": (
        "Add a redundant path or fallback service so this node is not "
        "the only option at its pipeline stage."
    ),
    "AMPLIFICATION_RISK": (
        "Add circuit breakers or bulkheads upstream of this node to "
        "prevent failures from cascading to all downstream dependents."
    ),
    "CONVERGENCE_SINK": (
        "Consider adding a read replica, cache layer, or secondary "
        "instance so upstream services are not all blocked by one target."
    ),
    "DEEP_BOTTLENECK": (
        "Add health checks and timeouts. Deep bottlenecks are hard to "
        "diagnose from edge monitoring — ensure this node has dedicated alerting."
    ),
    "MONITORING_GAP_CANDIDATE": (
        "Ensure this node has dedicated monitoring. It sits on critical "
        "paths but is not at the service edge, so it may be missing from "
        "your dashboards."
    ),
}


def _suggest_actions(categories: dict[str, list["RiskEntry"]]) -> list[str]:
    """Generate actionable recommendations from risk categories."""
    actions = []
    for cat, entries in categories.items():
        suggestion = _ACTION_MAP.get(cat)
        if suggestion:
            node_names = ", ".join(sorted({e.node for e in entries}))
            actions.append(f">> {node_names}: {suggestion}")
    return actions


@dataclass
class SemanticResult:
    """Result of a 6D structural encoding."""

    vectors: dict[str, list[float]]
    graph_info: dict[str, Any]
    encoding_time_ms: float
    risks: list[RiskEntry] = field(default_factory=list)

    def __getitem__(self, node: str) -> list[float]:
        return self.vectors[node]

    def dimensions(self, node: str) -> dict[str, float]:
        """Return named dimensions for a node."""
        v = self.vectors[node]
        return dict(zip(DIMENSION_NAMES, v))

    @property
    def nodes(self) -> list[str]:
        """All node names."""
        return list(self.vectors.keys())

    @property
    def table(self) -> str:
        """Formatted table sorted by criticality (highest first)."""
        header = f"{'Node':<35} {'Depth':>6} {'Indep':>6} {'Hier':>6} {'Thru':>6} {'Crit':>6} {'Fan':>6}"
        sep = "-" * len(header)
        rows = sorted(
            self.vectors.items(),
            key=lambda x: x[1][4],  # criticality index
            reverse=True,
        )
        lines = [header, sep]
        for node, v in rows:
            name = node if len(node) <= 35 else node[:32] + "..."
            lines.append(
                f"{name:<35} {v[0]:>6.3f} {v[1]:>6.3f} {v[2]:>6.3f} {v[3]:>6.3f} {v[4]:>6.3f} {v[5]:>6.3f}"
            )

        # Add interpretive key
        lines.append("")
        lines.append("Key: Depth=pipeline position, Indep=lateral redundancy (0=chokepoint),")
        lines.append("     Hier=module/community, Thru=traffic share, Crit=path dependency,")
        lines.append("     Fan=broadcaster(1) vs aggregator(0). All values 0-1.")
        return "\n".join(lines)

    def json(self) -> dict[str, Any]:
        """Full result as a JSON-serializable dict."""
        return {
            "vectors": self.vectors,
            "graph_info": self.graph_info,
            "encoding_time_ms": self.encoding_time_ms,
            "risks": [r.json() for r in self.risks],
        }
