# License FAQ

Common questions about the SemanticEmbed SDK license. The license itself
is in [LICENSE](LICENSE).

---

## Is this open source?

**No.** The SDK is **proprietary software with public source code**. The
source is on GitHub for adoption velocity (so you can read it, fork it
locally, and integrate it without friction), but the license does not
grant the rights an OSI-approved open-source license would.

This is the same pattern Stripe, Snowflake (`snowflake-connector-python`),
and Anthropic (TypeScript SDK) use for their official client libraries.
It's "source-available", not "open source".

---

## Can I use it commercially?

**Yes — within the free tier.** Graphs up to 50 nodes per request are
free for any use including commercial. No signup, no API key required.

For graphs larger than 50 nodes, you need a paid license. Email
**jeffmurr@seas.upenn.edu** for pricing.

---

## Can I fork the repo? Modify the code?

You can fork the repo and modify your local copy for your own internal
use, debugging, integration, or to send a PR back. You can't redistribute
modified versions, package a derivative SDK, or relicense the source.
The upshot: hack on it freely; don't ship a fork as your own product.

---

## What's actually proprietary?

Two things:

1. **The 6D encoding algorithm.** It runs server-side at the SemanticEmbed
   cloud API; it's not in this repo. Patent application
   [#63/994,075](#patent) covers the encoding method.
2. **The SDK code in this repo.** All rights reserved per LICENSE.txt;
   "All rights reserved" means the standard copyright defaults, modified
   only by the explicit grants in the license.

The SDK is a thin HTTP client + edge parsers. Reading the SDK source
gives you no information about the encoding algorithm — that's the whole
point of the architecture.

---

## What if my company has a strict OSS-only policy?

Talk to us. The SDK is proprietary but not adversarial — we've been
through procurement reviews where the legal team's primary concern was
"is this going to disappear?" (answer: paid customers get an escrow
clause; free-tier doesn't but everything is also pinned on PyPI). Email
**jeffmurr@seas.upenn.edu**.

---

## <a name="patent"></a>Patent

US Provisional Patent Application **#63/994,075**, filed
**2 March 2026**, covers the 6D structural encoding method, the risk
classification rules, and the system architecture (thin client + cloud
encoding service).

The patent application is in prosecution — it has not yet issued. The
SDK is shipped and supported regardless of patent timing.

---

## Free tier specifics

- **Hard limit:** 50 unique nodes per `encode()` call. Fewer than 2
  edges raises `ValueError`.
- **No rate limit on the wire** for the free path, but the SDK's
  retry-once policy and the server's tier policy together cap practical
  burst rate. If you're hitting rate limits, you're probably ready for
  a paid license anyway.
- **No signup, no email collection.** The free path doesn't even know
  who you are.

---

## Paid tier

- Larger graphs (configurable per license).
- Continuous monitoring (drift detection, scheduled re-encodes).
- CI/CD gating (block PRs that worsen structural risk past a threshold).
- Priority support, SLA, on-prem deployment options.

Pricing is bespoke depending on node count + monitoring frequency.
Email **jeffmurr@seas.upenn.edu** with your use case.

---

## More questions

Anything not covered here: **jeffmurr@seas.upenn.edu**.
