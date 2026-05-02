# Validation Methodology

This document explains how the **79.6% topology hit rate** claim in the
README was produced. The reproduction harness itself runs against a live
Dynatrace tenant (and lives in our private repo for that reason), but the
methodology, the fairness controls, and the math are public.

---

## Claim, restated precisely

> Out of **569 topology-relevant incidents** that occurred over a
> **30-day window** in a **108-service production Dynatrace environment**,
> **453 (79.6%)** affected nodes that 6D structural analysis had flagged
> as **risky** — based on the **call graph alone**, computed **before**
> any incident occurred.

Three things make this defensible rather than trivial:

1. The flagging happened **before** the incidents (no data leakage).
2. We restricted ground truth to **topology-relevant incidents** (no
   counting CPU spikes that have nothing to do with the call graph).
3. We compared against a stable baseline (see "Fairness controls" below).

---

## Inputs

**Topology snapshot:** services + their `fromRelationships.calls` from
Dynatrace Smartscape (Environment API v2, `entitySelector=type("SERVICE")`).
Captured once at the start of the 30-day window. 108 unique services,
161 directed edges. Same data anyone with a Dynatrace tenant and the SDK
can pull:

```python
from semanticembed import live
edges = live.from_dynatrace(env_url=..., api_token=...)
```

**Ground truth:** Dynatrace problems from the same 30-day window
(`/api/v2/problems`). 1,247 total problems, of which **569 were
topology-relevant** after filtering (see "What we filtered" below).

---

## Risk flags

The SDK call:

```python
result = encode(edges)             # 6D vectors per service
risks = report(result)             # structural risk classifications
```

Returns risk entries with categories `SINGLE_POINT_OF_FAILURE`,
`DEEP_BOTTLENECK`, `AMPLIFICATION_CASCADE`, `CONVERGENCE_SINK`,
`MONITORING_GAP_CANDIDATE`. Each entry has a `node`, a `category`, and a
`severity` (`critical` / `warning` / `info`). The classification
thresholds run server-side; the SDK only sees the labels.

For this validation, we considered a node **flagged** if it had any
`critical` or `warning` severity entry. **25 of 108 services** were
flagged.

---

## The match

For each of the 569 topology-relevant problems we asked: does the
`affectedEntities` list of the problem contain at least one node that
the SDK flagged?

- **453 problems → yes** (79.6%)
- **116 problems → no** (20.4%)

That's the headline number.

A more useful breakdown:

| Outcome | Count | What it means |
|---|---|---|
| **Confirmed** | 15 of 25 flagged services hit at least one problem | 60% of flags landed |
| **Early warning** | 10 of 25 flagged services had no problems in the window | structural risk that hadn't materialized yet |
| **Hits-on-flagged** | 453 of 569 problems | 79.6% topology hit rate |
| **Misses** | 116 of 569 problems | problems on services we hadn't flagged |

The "early warning" bucket is what makes this interesting: 10 services
were flagged structurally but had clean 30-day records. They're the
candidates for the next 30-day window — which becomes the next
prospective test.

---

## What we filtered ("topology-relevant")

A problem entered the ground truth set if **any** of these held:

- The problem title or description mentioned a service name (matches a
  node in the topology).
- The problem's `affectedEntities` list contained one or more services
  in the topology.
- The problem category was one of: `AVAILABILITY`, `ERROR`,
  `RESOURCE_CONTENTION`, `SLOWDOWN` (excludes log alerts and synthetic
  monitor failures unrelated to service topology).

Out-of-scope (filtered out): browser-side errors, certificate-expiry
alerts, synthetic-monitor flakiness, infrastructure problems on hosts
without a registered service, and 78 problems that couldn't be matched
to a topology entity at all.

The filter is conservative — it errs toward keeping problems in the
ground truth, which makes the 79.6% rate **harder** to achieve, not
easier.

---

## Fairness controls

Three things we did to avoid cooking the number:

1. **Pre-registration of flags.** The 25 risk flags were generated and
   stored before the ground-truth window started. We did not re-run the
   classifier after seeing problems and pick the best run.
2. **No incident-history feedback.** The SDK input was the topology
   snapshot only. No metric data, no historical incident counts, no
   alert rules. The same algorithm that runs on a brand-new repo's
   `docker-compose.yml` ran here.
3. **Comparison to coin-flip baseline.** If we'd flagged 25/108 services
   uniformly at random, the expected hit rate (probability that a
   random problem lands on at least one of 25 random services) would be
   ~46% under realistic problem-affected-entity distributions on this
   tenant. 79.6% is **+33 points** above chance.

A stronger comparison would be against degree centrality alone. We ran
that too: degree centrality flagged the top-25 by in-degree, and got
**61.0%** topology hit rate on the same 569 problems. 6D's 79.6% is
**+18.6 points** above the most obvious alternative — that's the
"orthogonal axes capture signals centrality misses" claim, made
concrete.

---

## Reproducibility

You can reproduce a similar experiment on your own infrastructure with
publicly available tools:

1. **Snapshot your topology** — pull a service-call graph from your APM
   (`live.from_dynatrace`, `live.from_honeycomb`, `live.from_datadog`)
   or static infrastructure parsers (`extract.from_directory`).
2. **Encode** — `result = encode(edges)`; collect the risk report.
3. **Wait** — let your problem / alert / incident system run for the
   chosen window without re-classifying.
4. **Match** — for each incident in the window, check whether any
   `affectedEntities` entry overlaps the SDK's flagged-node set.
5. **Compare** — compute hit rate, run a degree-centrality baseline as
   a sanity check.

We're glad to walk a design partner through this on their own data;
email **jeffmurr@seas.upenn.edu** with `[validation]` in the subject.

---

## Why the full reproduction script isn't public

The matching/scoring code that produced the 79.6% number sits in our
private repo (`jmurray10/6d-sdk`) because:

- It hardcodes the Dynatrace tenant we ran the test against.
- It includes the full server-side risk classifier (the thresholds and
  scoring rules that constitute trade secret per Patent #63/994,075).
- The Dynatrace problems data contains customer-identifiable context.

Everything that *isn't* trade secret — the methodology, the topology
input, the public Dynatrace API calls, the matching logic — is
documented above and reproducible end-to-end with this SDK.

---

## Caveats

- **Single-tenant result.** This is one 30-day window on one tenant. We
  haven't run it across N tenants because we don't have N tenants.
  Hit rate on your environment will vary. If you run it, we'd love to
  hear what number you get.
- **Hit rate ≠ precision.** 79.6% says "of 569 incidents, 453 were on
  flagged nodes." It doesn't say "every flagged node had an incident."
  60% of flags landed (15 of 25); the other 40% are early warnings.
- **Topology can lie.** Smartscape can miss async / queue-mediated calls
  where there's no direct HTTP relationship. Your structural risk graph
  is only as complete as the call graph you feed it.

---

## Questions

Email **jeffmurr@seas.upenn.edu** — happy to walk through the design or
run a similar experiment on your data.
