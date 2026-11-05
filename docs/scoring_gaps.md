# Hosted scoring behavior

Risk labels are not computed in this repository. `semanticembed.report`
prints `result.risks` from `POST /api/v1/encode`, and the client forwards
the edge list unchanged. The three cases below come from the service, not
from extractor or client bugs.

The response metadata is `n_nodes`, `n_edges`, and `max_depth`. There is
no kernel-time field. `encoding_time_ms` on the client is the HTTP wall
clock.

## Voting-app shape: empty report

Edges: `vote→redis`, `worker→redis`, `worker→db`, `result→db`.

The service returns no risk flags for this graph. That is the expected
result, not a missed finding. Larger graphs with the same pattern can be
flagged.

## Identical twins: one of the pair is flagged

Edges: `gateway→s1`, `gateway→s2`, `s1→db`, `s2→db`.

`s1` and `s2` play the same role, but only one of them gets the low
**independence** value and the `SINGLE_POINT_OF_FAILURE` flag. Both
still receive `MONITORING_GAP_CANDIDATE` and `DEEP_BOTTLENECK`.
Reordering the edge list does not move the flag. Renaming the nodes can.
Read a flag on one twin as applying to the whole set.

```python
edges = [
    ("gateway", "s1"),
    ("gateway", "s2"),
    ("s1", "db"),
    ("s2", "db"),
]
result = encode(edges)
# One of s1 / s2 is flagged. Reordering the edges keeps it on the same node.
```

## Cyclic graphs: not every edge is scored

When the input has cycles, some edges are not scored. Compare `result.graph_info["edges"]` with the number of
edges you sent. On `open_deep_research`, which has mutual tool loops
(`supervisor↔supervisor_tools`, `researcher↔researcher_tools`), fewer edges
are scored than sent, and flags that depend on those loops do not appear.

## Free tier

A 50-node chain encodes. A 51-node chain raises `NodeLimitError` in the
client with no HTTP call. A 100-node kernel time cannot be measured on
this tier, and the API does not return one.
