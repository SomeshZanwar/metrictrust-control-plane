# Architecture notes

## Decision flow (one action, start to finish)

1. **Agent proposes an action** — `POST /actions/propose` with an agent id/API
   key, an action type (`update_experiment_rollout`), a resource
   (`experiment/onboarding-v4`), and parameters (`requested_percentage`).
2. **Evidence Broker builds an Evidence Bundle** (`app/evidence.py`):
   - Parses the real `run_results.json` dbt produced on the last `dbt run` /
     `dbt test` to get critical test pass/fail counts and the
     assignment-integrity test result specifically.
   - Queries the dbt-built `fct_experiment_outcomes` table directly in DuckDB
     and hashes the exact rows returned — this is the "dataset snapshot" the
     decision is bound to, not a description of the dataset.
   - Looks up the requested metric in `config/metrics_registry.yaml` for its
     approval status and a hash of its definition.
   - Reads a guardrail feed (`evidence_store/guardrails.json` in this
     implementation — a live observability query in production).
   - Hashes the whole bundle into `bundle_hash`, deliberately excluding
     `source_freshness_minutes` (see the comment in `evidence.py` — freshness
     is a live gate, not part of evidence identity).
3. **Policy Engine evaluates** (`app/policy.py`): loads every rule in
   `policies/*.yaml`, checks all `forbid` rules first (any match → `DENY`),
   then `permit` rules (any match → `PERMIT`, i.e. within the agent's
   autonomous authority), and otherwise defaults to `REQUIRE_APPROVAL`. The
   default is "ask a human," never "allow" — an unrecognized action type
   fails closed, not open.
4. **If `REQUIRE_APPROVAL`**: an `Approval` row is created
   (`app/approvals.py`) with the evidence bundle hash captured at request
   time. When a human approves it (`POST /approvals/{id}/decide`), the
   evidence is **rebuilt from scratch** and compared against that captured
   hash before a permit is issued. If they don't match, the approval is
   rejected as stale — the whole point of binding approval to evidence
   instead of just recording that *an* approval happened.
5. **Permit issuance** (`app/security.py` + `app/permits.py`): an RS256-signed
   JWT is minted with a single-use nonce, a short expiry (10 minutes by
   default), and claims binding it to the specific action, resource,
   parameters hash, evidence bundle hash, metric definition hash, dataset
   snapshot id, and policy bundle hash that authorized it.
6. **Execution** (`app/executor.py`): the protected executor — the only
   component with "write" access to the feature-flag store — verifies the
   permit's signature, audience, expiry, and issuer, then checks the nonce
   against the database to reject replay of an already-consumed permit. Only
   then does it mutate the store.
7. **Post-execution guardrail check**: immediately after mutating the store,
   the executor re-reads the guardrail feed. If it shows a breach, the
   change is automatically rolled back to its previous value and the receipt
   records `ROLLED_BACK` instead of `SUCCESS`.
8. **Receipt + audit**: every step above is persisted, and `GET
   /actions/{id}` reconstructs the full trail — evidence, policy decision,
   approval (if any), permit, and receipt — from that one id.

## Why forbid-first, fail-closed

A permit rule matching means "the agent has autonomous authority for this,"
not "nothing is wrong." Checking forbid rules first means a stale-data
`forbid` rule always wins over a bounded-autonomy `permit` rule for the same
action — an agent's autonomy is a *ceiling*, not an override of data-quality
gates.

## Why the executor is a separate trust boundary from the API

`app/main.py` and `app/executor.py` currently run in the same process for
simplicity, but the credentials to mutate the feature-flag store are only
ever read inside `execute_permit()`, which is unreachable without a permit
that passed full cryptographic verification. In a production deployment
these would be genuinely separate services with separate credentials (see
`ROADMAP.md`) — the code is already structured so that split doesn't require
rewriting the verification logic, only moving where it runs.

## Known simplifications in the demo guardrail feed

`evidence_store/guardrails.json` is a static JSON fixture, not a live
observability query. `scripts/demo.py` flips it between `PASS` and `FAIL` to
demonstrate the rollback path deterministically. In production this would be
a query against the same metrics backend that powers alerting (see
`ROADMAP.md`).
