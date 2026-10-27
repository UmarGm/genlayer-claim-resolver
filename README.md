# ClaimResolver — multi-source fact resolution primitive for GenLayer

A reusable Intelligent Contract that settles a **YES/NO claim** using several
independent web sources, with a consensus rule designed around *structured*
output instead of free-text LLM answers.

Typical uses: prediction-market settlement, bounty or escrow release conditions,
"did X happen by date Y" oracles, DAO fact checks. Other contracts can call
`create_claim` / `resolve` / `challenge` / `get_claim` and treat the result as an
on-chain fact.

## What's new in v2

| Change | Why |
|---|---|
| **Domain independence rule**: every source must come from a different domain (`www.` and upper/lower case are normalised away) | Before, five pages of one website counted as five "independent" sources. Now a quorum really means several different publishers agree |
| **`challenge(claim_id, extra_sources)`** | A claim that closed as `CLOSED_UNRESOLVED` was a dead end. Its creator can now add 1–3 sources from **new** domains, once per claim (max 7 sources in total), and re-open it for 3 more attempts |
| `challenges` counter in `get_claim` | Makes it visible on-chain whether a claim has already used its challenge |
| Unit tests for host normalisation, the domain rule, the challenge rules and 6–7 source quorums | 24 tests in total, all on the deterministic core |

Everything from v1 (quorum rule, validator equivalence rule, attempt limit) is
unchanged, so v1 claims keep their meaning.

## Why this is more than a thin LLM wrapper

| Concern | Design choice |
|---|---|
| Single point of failure | 2–5 independent HTTPS sources per claim, each from a different domain; one source can never decide the outcome |
| LLM text never matches exactly | Validators compare only `{verdicts: [...], final: ...}`, never prose |
| Dishonest or buggy leader | Validator checks the leader's `final` really follows from the leader's own per-source verdicts |
| Flaky page load / borderline answer | Equivalence tolerates **one** differing source verdict, but never a different final outcome |
| Guessing under uncertainty | No quorum → `UNRESOLVED` instead of a forced answer |
| Endless re-runs | Max 3 attempts, then the claim closes as `CLOSED_UNRESOLVED` |
| Dead end after an inconclusive round | One creator-only `challenge()` with extra sources from new domains |
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

Quorum rule: `max(2, ceil(2n/3))` sources must agree (2→2, 3→2, 4→3, 5→4,
6→4, 7→5), and the winning side must also strictly outnumber the other.

## Challenge flow

```
create_claim ──► OPEN ──resolve──► RESOLVED (YES / NO)
                  │
                  └─ 3 unresolved attempts ─► CLOSED_UNRESOLVED
                                                  │
                          challenge(extra sources from new domains)
                                                  │
                                                  ▼
                              OPEN again (attempts reset, 1 challenge max)
```

Rules enforced by `challenge`:
- only the claim creator can call it,
- only while the status is `CLOSED_UNRESOLVED`,
- once per claim (`MAX_CHALLENGES = 1`),
- 1–3 extra sources, all `https://`, each from a domain not used yet,
- at most 7 sources in total after the challenge.

It is creator-only on purpose: if anyone could add sources, a third party could
stack a claim with sources it controls. The trade-off is that the creator is
the one choosing the extra evidence, so consumers who need neutrality should
treat a challenged claim with the same scepticism as the creator's own sources.
The quorum stays two thirds, so extra sources must still clearly agree.

## State design

`TreeMap[u256, Claim]` plus a `next_id` counter. A `Claim` stores creator,
question, source list (fixed at creation, extended only by one challenge),
status, final verdict, last per-source verdicts, attempt count and challenge
count. Lifecycle: `OPEN → RESOLVED` or `OPEN → CLOSED_UNRESOLVED → (challenge)
→ OPEN`.

## Interface

| Method | Type | Description |
|---|---|---|
| `create_claim(question, sources)` | write | Opens a claim, returns its id |
| `resolve(claim_id)` | write | Runs consensus; returns `YES`, `NO` or `UNRESOLVED` |
| `challenge(claim_id, extra_sources)` | write | Creator only: adds 1–3 sources from new domains to a `CLOSED_UNRESOLVED` claim and re-opens it; returns the new source count |
| `get_claim(claim_id)` | view | Full claim record incl. per-source verdicts and challenge count |
| `get_claim_count()` | view | Number of claims created |

## Try it in GenLayer Studio

1. Open Studio, create a new file, paste `claim_resolver.py`, deploy (no constructor args).
2. `create_claim` with:
   - `question`: `Was Python 3.12 released in 2023?`
   - `sources`: `["https://docs.python.org/3/whatsnew/3.12.html", "https://en.wikipedia.org/wiki/History_of_Python"]`
3. `resolve` with `claim_id = 0`, wait for consensus.
4. `get_claim` with `claim_id = 0` and inspect `verdict` and `source_verdicts`.

Domain rule check: `create_claim` with two URLs from the same website (for
example two `en.wikipedia.org` pages) now fails with
`sources must come from different domains`.

Challenge check: use a question the sources cannot settle, call `resolve` three
times until `get_claim` shows `CLOSED_UNRESOLVED`, then call
`challenge(0, ["https://<new-domain>/page"])` from the same account. The claim
returns to `OPEN` with `attempts = 0` and `challenges = 1`.

## Tests

The deterministic core (quorum rule, validator equivalence rule, domain
independence, challenge validation, input validation) is plain Python and
covered by unit tests, including a forged-leader case, the one-flaky-source
tolerance and 6–7 source quorums:

```
python -m pytest tests/ -v
```

(The tests extract the block between the `pure logic` markers, because the
`genlayer` module only exists inside GenVM.) The LLM, web and storage steps,
including `challenge()`, are covered by the Studio walkthrough above.

## Notes

- The runner hash on the first line must be a pinned version; GenLayer networks
  reject `latest`/`test` aliases. Check Studio docs for the current hash if
  deployment complains.
- The domain rule compares hosts, so `docs.example.org` and `blog.example.org`
  count as different domains. A public-suffix list would be stricter but is too
  heavy to ship inside a contract.
- Possible extensions: per-source weights, allowed-domain allowlists, payable
  escrow built on top.
