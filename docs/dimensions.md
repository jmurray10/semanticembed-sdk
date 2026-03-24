# The Six Dimensions

SemanticEmbed computes six independent structural measurements for every node in a directed graph. Together, these six numbers form a coordinate vector in 6-dimensional Euclidean space that fully describes the node's structural role.

---

## Overview

| # | Dimension | What It Measures | Range |
|---|-----------|-----------------|-------|
| 1 | **Depth** | Position in the execution pipeline | 0.0 -- 1.0 |
| 2 | **Independence** | Lateral redundancy at the same stage | 0.0 -- 1.0 |
| 3 | **Hierarchy** | Module or group membership | 0.0 -- 1.0 |
| 4 | **Throughput** | Fraction of total traffic through this node | 0.0 -- 1.0 |
| 5 | **Criticality** | Fraction of end-to-end paths depending on this node | 0.0 -- 1.0 |
| 6 | **Fanout** | Broadcaster (1.0) vs aggregator (0.0) | 0.0 -- 1.0 |

---

## Depth

Where a node sits in the execution pipeline. Entry points are 0.0, deepest sinks are 1.0.

A failure at low depth cascades forward through more of the graph. A failure at high depth has limited downstream impact.

---

## Independence

How many other nodes operate at the same pipeline stage. Measures lateral redundancy.

A node with independence 0.0 is the only node at its depth level -- a structural chokepoint. A node with high independence has many parallel peers.

**This dimension has no equivalent in standard graph centrality measures.** Near-zero correlation with all standard centrality metrics. It captures a structural property that the entire field's standard toolkit cannot see.

---

## Hierarchy

Which module, community, or logical group a node belongs to. Computed via Louvain community detection on the undirected graph.

Nodes in the same community have similar hierarchy values. Cross-community dependencies show up as connections between nodes with different hierarchy values -- these are integration risk points. Independent of depth: nodes at the same pipeline stage can belong to different modules.

---

## Throughput

What fraction of total traffic flows through this node, based on connectivity relative to the graph.

Independent of depth: a deep node can have high or low throughput. High throughput combined with low independence indicates a hidden bottleneck.

---

## Criticality

How many end-to-end paths through the graph depend on this node.

A node with criticality 0.5 sits on half of all source-to-sink paths. If it fails, half of all end-to-end flows break. Independent of throughput: a low-traffic node can be highly critical if it bridges two large subgraphs.

---

## Fanout

Whether a node amplifies (broadcasts to many downstream) or aggregates (collects from many upstream).

High fanout = amplification risk. A failure here multiplies across all downstream dependents. Low fanout = convergence sink. Many upstream services depend on this single point.

---

## Independence of Dimensions

The six dimensions capture complementary structural properties. Each dimension provides information that aids structural analysis:

- A deep node can have high or low throughput
- A high-traffic node can sit on one path or many paths
- A node at any depth, throughput, or criticality can be a broadcaster or aggregator
- Independence has near-zero correlation with all standard centrality measures
- Hierarchy (community membership) is independent of pipeline position

The independence dimension is the most novel -- it captures a structural property (lateral redundancy) that no standard graph metric can measure.

Adding more dimensions (7, 8, ...) was tested and hurt performance -- the extra dimensions carried redundant information. Six is the natural dimensionality of the structural property space for directed computational graphs.

---

## Structural Risk Patterns

| Pattern | Dimensions | Risk |
|---------|-----------|------|
| **Amplification risk** | High fanout + high criticality | Failure cascades to many services across many paths |
| **Convergence sink** | Low independence + low fanout | Many services depend on one aggregation point |
| **Structural SPOF** | Low independence + high criticality | Only node at its depth, on most paths |
| **Hidden bottleneck** | High throughput + low independence | Carries most traffic with no redundancy |
