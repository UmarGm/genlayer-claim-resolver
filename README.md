# ClaimResolver — multi-source fact resolution primitive for GenLayer

A reusable Intelligent Contract that settles a **YES/NO claim** using several
independent web sources, with a consensus rule designed around *structured*
output instead of free-text LLM answers.

Typical uses: prediction-market settlement, bounty or escrow release conditions,
"did X happen by date Y" oracles, DAO fact checks. Other contracts can call
`create_claim` / `resolve` / `get_claim` and treat the result as an on-chain
fact.

## Why this is more than a thin LLM wrapper

| Concern | Design choice |
|---|---|
| Single point of failure | 2–5 independent HTTPS sources per claim; one source can never decide the outcome |
| LLM text never matches exactly | Validators compare only `{verdicts: [...], final: ...}`, never prose |
| Dishonest or buggy leader | Validator checks the leader's `final` really follows from the leader's own per-source verdicts |
| Flaky page load / borderline answer | Equivalence tolerates **one** differing source verdict, but never a different final outcome |
| Guessing under uncertainty | No quorum → `UNRESOLVED` instead of a forced answer |
| Endless re-runs | Max 3 attempts, then the claim closes as `CLOSED_UNRESOLVED` |
| Prompt injection from web pages | Page text is passed as untrusted data and the model may only return a fixed enum, anything else becomes `UNDETERMINED` |

## How consensus is used

`resolve(claim_id)` uses `gl.vm.run_nondet_unsafe(leader_fn, validator_fn)`:

1. **Leader** fetches every source (`gl.nondet.web.render`), asks the LLM for a
   strict per-source verdict (`YES` / `NO` / `UNDETERMINED`), then applies a
   deterministic quorum rule (`aggregate`).
2. **Each validator** re-runs the same pipeline independently and accepts the
   leader only if all of these hold (`results_equivalent`):
   - leader's verdict list is well-formed and uses only valid values,
   - `aggregate(leader.verdicts) == leader.final` (no forged outcome),
   - validator's own `final` equals the leader's `final`,
   - at most one per-source verdict differs.

Quorum rule: `max(2, ceil(2n/3))` sources must agree (2→2, 3→2, 4→3, 5→4), and
the winning side must also strictly outnumber the other.

## State design

`TreeMap[u256, Claim]` plus a `next_id` counter. A `Claim` stores creator,
question, source list (fixed at creation, so it can't be swapped after the
fact), status, final verdict, last per-source verdicts and attempt count.
Lifecycle: `OPEN → RESOLVED` or `OPEN → CLOSED_UNRESOLVED`.

## Interface

| Method | Type | Description |
|---|---|---|
| `create_claim(question, sources)` | write | Opens a claim, returns its id |
| `resolve(claim_id)` | write | Runs consensus; returns `YES`, `NO` or `UNRESOLVED` |
| `get_claim(claim_id)` | view | Full claim record incl. per-source verdicts |
| `get_claim_count()` | view | Number of claims created |

## Try it in GenLayer Studio

1. Open Studio, create a new file, paste `claim_resolver.py`, deploy (no constructor args).
2. `create_claim` with:
   - `question`: `Was Python 3.12 released in 2023?`
   - `sources`: `["https://docs.python.org/3/whatsnew/3.12.html", "https://en.wikipedia.org/wiki/History_of_Python"]`
3. `resolve` with `claim_id = 0`, wait for consensus.
4. `get_claim` with `claim_id = 0` and inspect `verdict` and `source_verdicts`.

## Tests

The deterministic core (quorum rule, validator equivalence rule, input
validation) is plain Python and covered by unit tests, including a forged-leader
case and the one-flaky-source tolerance:

```
python -m pytest tests/ -v
```

(The tests extract the block between the `pure logic` markers, because the
`genlayer` module only exists inside GenVM.) The LLM and web steps are covered
by the Studio walkthrough above.

## Notes

- The runner hash on the first line must be a pinned version; GenLayer networks
  reject `latest`/`test` aliases. Check Studio docs for the current hash if
  deployment complains.
- Possible extensions: per-source weights, allowed-domain allowlists, a
  `challenge()` flow with extra sources, and payable escrow built on top.
