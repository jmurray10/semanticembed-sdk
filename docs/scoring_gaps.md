# Scoring gaps (hosted API)

Risk labels are not computed in this repository. `semanticembed.report`
prints `result.risks` from `POST /api/v1/encode`. The response metadata
observed on 2026-11-04 is `n_nodes`, `n_edges`, and `max_depth`. There is
no kernel-time field. This file records what that API returned. Nothing
here changes the service.

Repro edges are in `corpus/manifest.json` under `risk_cases`. Agreement is
the Jaccard overlap of `(node, category)` pairs. Run:

```bash
python scripts/corpus_score.py --split tuning --live-api --skip-drift
```

## Where the logic lives

`src/semanticembed/client.py` posts the edge list and copies `risks` onto
`SemanticResult`. `src/semanticembed/models.py` formats those records.
`docs/validation_methodology.md` already says the classifier thresholds
are server-side. Confirmed by reading both modules: there is no local
threshold, tie-break, or category rule to change.

## What the API returned

Captured 2026-11-04 against `https://semanticembed-api-production.up.railway.app`.
No license key. Round trip about 0.3–0.4 s. `encoding_time_ms` on the
client is that wall clock.

### example-voting-app shape

Edges: `vote→redis`, `worker→redis`, `worker→db`, `result→db`.
`redis` and `db` each have two callers.

Hand label: `CONVERGENCE_SINK` on both `redis` and `db`.

API: **no structural risks**. Agreement **0**. The vectors still separate
the twins: `db` independence 0.000, `redis` independence 1.000, both
criticality 0. The tie-break is already in the coordinates, and the
zero-criticality gate then drops both.

### Symmetric services

Edges: `gateway→s1`, `gateway→s2`, `s1→db`, `s2→db`.
`s1` and `s2` have the same degree.

Hand label: `SINGLE_POINT_OF_FAILURE` on both.

API: `SINGLE_POINT_OF_FAILURE` on `s1` only (`independence=0.00`).
`s2` is `independence=1.00` with the same criticality 0.062.
Both get `MONITORING_GAP_CANDIDATE` and `DEEP_BOTTLENECK`.
Agreement against the two-SPOF label: **1/6 ≈ 0.17**.

### open_deep_research cycles

The 16 extracted edges include `supervisor↔supervisor_tools` and
`researcher↔researcher_tools`.

Hand label used the closest published category, `AMPLIFICATION_RISK`,
on `supervisor` and `researcher`. The server has no cycle category.

API: **no structural risks**. Agreement **0**. Metadata `n_edges` was
**8**, not 16, so the service also dropped edges before scoring.

### Free tier

A 50-node chain encodes. A 51-node chain raises `NodeLimitError` in the
client with no HTTP call. A 100-node "<1 ms kernel" measurement cannot
be made on this tier, and the API does not return a kernel time anyway.

## Not changed

No production deploy. No threshold fitted to voting-app, to `s1`/`s2`,
or to `deep_researcher.py`.
