# Hosted scoring behavior

Risk labels are not computed in this repository. `semanticembed.report`
prints `result.risks` from `POST /api/v1/encode`. A live debug on main
`33f9a51` showed the SDK client forwards those three graphs correctly.
The earlier write-up treated designed server behavior as extractor or
client gaps. It was not.

The response metadata is `n_nodes`, `n_edges`, and `max_depth`. There is
no kernel-time field. `encoding_time_ms` on the client is the HTTP wall
clock. Nothing here changes the service.

## Voting-app shape is under the threshold

Edges: `vote→redis`, `worker→redis`, `worker→db`, `result→db`.
`redis` and `db` each have two callers.

`CONVERGENCE_SINK` fires live when a node has **3 or more** callers.
Two callers is below that threshold, so an empty report is the correct
result. The same shape with a third caller on each sink flags both
`redis` and `db`. This is threshold behavior, not a missed finding.

**Doc mismatch.** Several pages still describe a convergence sink as
"low independence + low fanout":

- `docs/getting_started.md` (key risk combinations)
- `docs/dimensions.md` (Structural Risk Patterns)
- `docs/output_format.md` (Risk Categories)
- the system prompt in `src/semanticembed/explain.py`

That phrase does not match the live rule (3 or more callers). Those
lines are corrected in the same change.

## Identical twins break ties lexically

Edges: `gateway→s1`, `gateway→s2`, `s1→db`, `s2→db`.

`s1` and `s2` are structurally identical. Within a depth layer the
independence axis breaks ties by node name, lexicographically.
`docs/dimensions.md` already states that. `s1` sorts before `s2`, so
`s1` gets independence 0 and the `SINGLE_POINT_OF_FAILURE` flag.
`s2` gets independence 1. Both still receive
`MONITORING_GAP_CANDIDATE` and `DEEP_BOTTLENECK`.

Permuting the edge list does not move the flag. Renaming the nodes
does: `s2`/`s1` swapped as names, or `a`/`b` in place of `s1`/`s2`,
puts the low independence value on whichever name sorts first.

```python
edges = [
    ("gateway", "s1"),
    ("gateway", "s2"),
    ("s1", "db"),
    ("s2", "db"),
]
result = encode(edges)
# SPOF node is s1. Reorder the four edges: still s1.
# Rename s1 -> b and s2 -> a: the SPOF moves to a.
```

## Cycles are removed before scoring

`open_deep_research` sends 16 edges, including
`supervisor↔supervisor_tools` and `researcher↔researcher_tools`.
The scorer breaks cycles and encodes the acyclic part. Metadata
`n_edges` is **8** of the 16 sent. Expecting `AMPLIFICATION_RISK` on
those mutual tool loops was wrong: the loops are not in the graph that
gets scored.

Open question: the cut is aggressive. A gentler Kahn-style removal of
back-edges keeps **13** of the 16. `docs/dimensions.md` describes
back-edge removal as Kahn's algorithm. The live cut on this graph is
stricter than that minimal removal. That alternative is not what the
service does today.

## Free tier

A 50-node chain encodes. A 51-node chain raises `NodeLimitError` in the
client with no HTTP call. A 100-node kernel time cannot be measured on
this tier, and the API does not return one.
