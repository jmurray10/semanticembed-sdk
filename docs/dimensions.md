# The Six Dimensions

SemanticEmbed computes six complementary structural measurements for every node in a directed graph. Together, these six numbers form a coordinate vector in 6-dimensional Euclidean space that summarizes the node's structural role under the invariance properties documented [below](#what-the-encoding-preserves).

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

**Empirically low correlation with standard graph centrality.** On a benchmark
of 4 reference topologies (Online Boutique, Sock Shop, AI agent pipeline,
CI/CD pipeline), Independence shows |r| < 0.15 against degree, betweenness,
closeness, and eigenvector centrality. Lateral redundancy is a structural
feature most centrality measures don't model directly; it's captured here as
a first-class axis. (The benchmark and correlation table are reproducible
from `examples/` plus the SDK's `extract.from_directory()`.)

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

## What the encoding preserves

The encoding map `f: G → R^(|V|×6)` (where `G` is a directed graph and the
output is a 6-tuple per vertex) has the following invariance properties.
These are stated formally so the algorithm's claims can be checked rather
than trusted:

1. **Vertex-isomorphism invariance.** Let `G = (V, E)` and `G' = (V', E')`
   with a bijection `π: V → V'` such that `(u, v) ∈ E ⇔ (π(u), π(v)) ∈ E'`.
   Then `f(G)[v] = f(G')[π(v)]` for every `v ∈ V`. Two graphs that differ
   only by node-relabeling produce identical 6D fingerprints (after the
   corresponding relabeling). **Sketch:** each axis is computed from
   structural quantities (topological depth, BFS-derived path counts,
   Louvain community indices, edge-weight aggregates) that are themselves
   defined modulo isomorphism. *Caveat:* the **independence** axis uses
   lexicographic ordering of nodes within a depth layer for determinism,
   which means renaming can shift the independence value within a layer
   even though the underlying lateral-redundancy structure is unchanged.
   This is a known limitation tracked for a future release.

2. **Self-loop and back-edge invariance.** Self-loops are silently dropped
   during edge normalization. Back-edges are removed by Kahn's DAG
   enforcement before any axis is computed. Adding or removing a self-loop
   or a single back-edge that doesn't change the DAG topology produces an
   identical encoding.

3. **Locality.** Two nodes that share `(in_neighbors, out_neighbors)`
   structure within a 2-hop neighborhood produce 6D vectors that differ
   by at most ε on the first five axes (depth / independence / hierarchy /
   throughput / criticality). Hierarchy can change discretely if Louvain
   assigns the nodes to different communities. This is observed
   empirically across the 4 benchmark topologies; not yet proved formally.

**What the encoding does NOT preserve:**

- **Edge weights for axes other than throughput.** Depth, independence,
  hierarchy, criticality, and fanout treat all edges equally. Throughput
  is the only weight-sensitive axis.
- **Backward-information.** Once the DAG is enforced, the back-edges
  removed are not represented anywhere in the encoding. A graph with
  cycles and its acyclic closure produce the same encoding.
- **Semantic labels.** Node names are used only for identity and
  ordering. The encoding is invariant under content-preserving renames
  (per property 1).

The encoding is **not** a lossless representation of `G`. It is a
6-dimensional summary chosen to capture properties that empirically
predict structural risk; the [validation methodology](validation_methodology.md)
documents that empirical claim.

---

## Why six dimensions

The six axes are the result of a design choice: each captures a structural
property that informs at least one of the [risk patterns below](#structural-risk-patterns).
We tested 7- and 8-axis variants during development and found:

- A 7th axis (we tried "edge betweenness sum") was strongly correlated
  (`r > 0.8`) with the existing throughput axis on the benchmark topologies
  and didn't improve risk-prediction quality measurably.
- An 8th axis (we tried "spectral gap of the local subgraph") added compute
  cost without a measurable lift on the same benchmark.

This is **not** a claim that 6 is the canonical dimensionality of
directed-computational-graph structure — it's the empirical sweet spot
under the design constraints (sub-millisecond compute, interpretable
axes, distinct risk-pattern coverage). A different objective function
might justify a different dimensionality.

---

## Why the dimensions are useful together

- A deep node can have high or low throughput — depth and throughput
  measure different things
- A high-traffic node can sit on one path or many paths — throughput and
  criticality measure different things
- A node at any depth / throughput / criticality can be a broadcaster
  (high fanout) or aggregator (low fanout)
- Independence has empirically low correlation with standard centrality
  measures — see the Independence section above for the benchmark
- Hierarchy (community membership) is empirically uncorrelated with
  pipeline position

---

## Structural Risk Patterns

| Pattern | Dimensions | Risk |
|---------|-----------|------|
| **Amplification risk** | High fanout + high criticality | Failure cascades to many services across many paths |
| **Convergence sink** | Low independence + low fanout | Many services depend on one aggregation point |
| **Structural SPOF** | Low independence + high criticality | Only node at its depth, on most paths |
| **Hidden bottleneck** | High throughput + low independence | Carries most traffic with no redundancy |
