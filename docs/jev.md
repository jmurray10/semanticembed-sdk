# Jev checks in CI

Three CI checks use [TypeSafe](https://docs.typesafe.ai)'s Jev model. Jev
answers yes/no questions about text we send and returns probabilities. Code
in `scripts/jev/` makes every decision. None of this runs in the published
package, and nothing a user installs talks to TypeSafe.

| Check | Workflow | Sends to TypeSafe | Fails the run when |
|---|---|---|---|
| Leak guard | `leak-guard.yml`, every pull request | the lines the PR adds | an added hunk explains hosted-service internals, or the check could not run |
| Drift check | `jev-drift.yml`, weekly | the invented cases in `scripts/jev/canary_cases.json` | Jev's answers moved from the stored baseline |
| Edge audit | `corpus.yml`, manual | the public corpus files and their extracted edges | never (report only); errors are reported |

All three need the secret `TYPESAFE_API_KEY`, stored in the GitHub environment
`jev` so that no other job can read it. The key is only put
in the `Authorization` header; it is never printed or logged. Only public
repository content is sent. Do not point these scripts at private code.

The model is pinned to `jev-1.14.0` (`scripts/jev/jev_client.py`), because
the thresholds below were measured on it. All question wording, context and
thresholds are in `scripts/jev/questions.py`.

## Leak guard

The scoring rules run on the hosted service and are private. Docs may say
what a value or flag **means**. They must not give a flag's numeric cutoff,
the steps that compute a value, how the input graph is changed before
scoring, or how ties are broken.

For each run of added lines (at most 120 lines), Jev answers four questions,
one per kind of leak, plus a subject question: "does this describe what the
hosted server does, or add code that does the server's work here?".

- Any of the four above 0.7: **leak**. The check fails, with an error on the line.
- Otherwise, any of the four at 0.3 or more: **review**. A warning on the line.
- Otherwise: pass.
- In the guard's own files (`scripts/jev/*.py`, `tests/test_jev_scripts.py`,
  this page), a leak also needs the subject answer at 0.3 or more, because
  they state the guard's own cutoffs. The list is exact paths in
  `leak_guard.py`.
- If Jev cannot be reached, or the key is missing, the check fails (exit 2).

The workflow runs the guard's code from the base branch, so a pull request
cannot change what runs with the key. Pull requests from forks get no
secrets; they need a maintainer's review for this.

To run it locally on your branch:

```bash
export TYPESAFE_API_KEY=...
python scripts/jev/leak_guard.py --base origin/main --head HEAD
```

### Measurements (2026-11-05, `jev-1.14.0`)

Hunks come from the public history of this repository. Leak labels were
written by hand before any Jev call. A "leak" hunk states the convergence
cutoff, the tie-break rule, or how cycles are cut.

| Set | Hunks | Leaks | Caught | False leaks | Warnings on clean hunks |
|---|---|---|---|---|---|
| Audit tuning commits (`a612cec`, `4f1cec9`) | 94 | 1 | 1 | 0 | 5 |
| Audit held-out commits (`33f9a51`, `26517a0`) | 87 | 15 | 15 | 0 | 1 |
| The security and Jev branches (all clean) | 94 | 0 | 0 | 0 | 13 |
| Invented cases (`canary_cases.json`) | 24 | 12 | 12 | 1 | 1 |

Cost: about $0.0001 per hunk.

Caveats:

- The held-out commits were also the audit's held-out set (2026-11-04), so
  the "any of the four" rule was chosen with them in view.
- The guard-file rule and the context sentence that says this repository
  is the client were chosen after seeing the invented cases and this
  branch's own hunks. A new set of labeled hunks is the next real test.
- The false leak on the invented cases is client code that sorts results
  for display and breaks ties by API order. Expect the guard to flag code
  that talks about breaking ties, even when it only orders output.
- Repeating a request moves answers by about 0.03. A few cases sit near a
  threshold.
- The rewritten notes on identical twins and cyclic input
  (`docs/scoring_gaps.md`, `docs/dimensions.md`, `corpus/manifest.json`) get
  warnings (0.45–0.60). They state what users see, not how the service
  decides.

## Drift check

`scripts/jev/drift_canary.py` runs the leak guard's questions over 24 fixed,
invented cases (12 leaks with made-up flag names, 12 clean) and compares
them with `scripts/jev/canary_baseline.json`. It fails when the answering
model differs from the baseline's, when a case's decision changes and its
answers moved more than 0.05, or when any answer moved more than 0.15.
`--also jev-latest` reports, without failing, how the moving alias answers.
That shows a new release before the pinned version is changed.

After a deliberate change to questions or thresholds, measure again, then:

```bash
python scripts/jev/drift_canary.py --write-baseline
```

## Edge audit

`scripts/jev/edge_audit.py` asks whether each extracted edge is real or a
parsing artifact, such as a URL scheme (`git`, `https`), a constraints file,
or a dependency group name read as a package. It runs on the public corpus
after `scripts/corpus_score.py`:

- **pinned**: every edge from the labeled files. All are labeled real, so
  any drop is a false alarm of the audit itself.
- **head**: edges that appear only at each repo's current HEAD. These have
  no labels, which is where a parser regression would show.

Rule: drop when `target_is_component < 0.3`, or `target_is_group > 0.7` and
`claim_shown < 0.3`; keep when `target_is_component > 0.7`; otherwise review.
It is report only and is not a client feature: in the client it would send
users' files to a third party.

Measured 2026-11-05: 12 of 12 junk edges dropped and 0 of 41 real edges
dropped on held-out fixtures (`requirements.txt` and `pyproject.toml` with
VCS URLs, constraints files and dependency groups). On the corpus, 0 of
113 real edges were dropped and 3 went to review.
