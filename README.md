# MetricTrust Control Plane

**Evidence-bound execution control for autonomous product-analytics agents.**

MetricTrust sits between an AI analytics agent and the systems it wants to act on
(feature flags, experiment rollouts). It does not just check whether an agent is
*allowed to call a tool* — it checks whether the specific action the agent is
proposing is backed by current, tested, approved evidence, and only then issues a
short-lived, signed, single-use **execution permit**. A separate, protected
executor accepts nothing from the agent directly and will only act on a valid
permit.

> An analytics agent proposes rolling an experiment from 20% to 50% because the
> treatment arm is outperforming control. MetricTrust doesn't evaluate whether the
> agent's explanation sounds convincing — it checks the dbt test results, the
> metric's approval status, the assignment-integrity test, and the agent's
> authority limits for this action. Within limits, it signs a permit
> automatically. Above the agent's limit, it routes to a human approver — and
> re-verifies the evidence hasn't moved *after* approval and *before* issuing the
> permit. After execution, a live guardrail check can still trigger an automatic
> rollback.

This repository is a working, tested implementation of that flow — not a slide
deck. `pytest` (21 tests), a scripted end-to-end demo, and a live dashboard all
run against real dbt artifacts and a real signed-JWT permit system.

---

## Why this exists

Data-observability tools can tell an agent whether data is fresh. Semantic
layers can tell it what a metric means. Agent frameworks can restrict which
tools an agent may call. None of them answer the actual question an enterprise
needs answered before letting an agent write to a production system:

> **Was this specific action authorized under the exact data, metric, and
> approval state that justified it — and is that still true right now?**

That's a narrower, harder problem than "is the data good" or "is the agent
allowed to call this tool," and it's the one this project is built around.

## What's real vs. what's scoped down

The original design for this project (see `docs/ORIGINAL_DESIGN.md`) specified a
full enterprise stack: Cedar policy engine, SPIFFE/SPIRE workload identity,
Temporal for durable workflows, a confidential-computing MCP gateway with TEE
attestation, Kubernetes, and a vendor-specific agent governance toolkit still in
public preview. That's a realistic *production* architecture — and an unrealistic
solo, one-to-two-month build.

This implementation keeps every property that actually matters (fail-closed
policy evaluation, evidence-bound signed permits, single-use replay protection,
approval-binding re-verification, automatic rollback on guardrail breach,
reconstructible audit trail) and replaces the heavy infrastructure with
smaller, real components that hold the same contract:

| Original design doc | This implementation | Why |
|---|---|---|
| Cedar policy engine | Custom YAML rule engine (`app/policy.py`) — same principal/action/resource/context shape, plain deterministic Python evaluation | No LLM or Rust toolchain dependency; the rule *shape* (forbid/permit, conditions) is a straight port, so swapping in real Cedar later is a policy-file change, not a rewrite |
| SPIFFE/SPIRE workload identity | Static per-agent API keys + RS256-signed permits | Real cryptographic signing (RSA-2048, single-use nonces) without standing up a SPIRE server for a solo project |
| Temporal durable workflows | Database-backed approval state machine (`app/approvals.py`) | Same contract (PENDING → APPROVED/DENIED/EXPIRED, survives restarts because it's in Postgres/SQLite, not memory) without an extra service to operate |
| cMCP / TEE attestation | Not implemented | Developer-preview technology; noted as a hardware-assurance upgrade path in `ROADMAP.md`, not something to fake |
| Kubernetes / Helm | Docker Compose + `uvicorn` | Right-sized for a single-service demo |
| Microsoft AGT | Not implemented | Public-preview vendor dependency; the interception/authority-check behavior it would provide is implemented directly in `app/routers/actions.py` |
| dbt Semantic Layer / MetricFlow | Flat YAML metric registry (`config/metrics_registry.yaml`) | Same *evidence question* (is this metric approved, what's its definition hash) without standing up the full semantic layer |

Nothing here fakes evidence. `dbt_project/` is a real dbt Core + DuckDB project;
`app/evidence.py` parses the actual `manifest.json` / `run_results.json` dbt
produces. The permits are real RS256-signed JWTs verified against a real public
key, with real single-use enforcement at the database layer. See
`ROADMAP.md` for the production upgrade path for each simplification above.

---

## Architecture

```
Product Analytics Agent
        |
        | POST /actions/propose  (agent_id, action, resource, parameters)
        v
+-------------------------------------------------------------+
|                  MetricTrust Control Plane                  |
|                                                               |
|  1. Evidence Broker   (app/evidence.py)                      |
|     - parses real dbt manifest.json / run_results.json       |
|     - queries the dbt-built fact table directly, hashes the  |
|       exact rows the decision will be based on               |
|     - reads metric registry + a live guardrail feed          |
|     - hashes the whole bundle -> evidence_bundle_hash         |
|                                                               |
|  2. Policy Engine     (app/policy.py)                         |
|     - deterministic YAML rules (policies/*.yaml)              |
|     - forbid rules checked first (fail-closed)                |
|     - DENY | REQUIRE_APPROVAL | PERMIT                        |
|                                                               |
|  3. Approval Workflow (app/approvals.py)                      |
|     - durable DB state machine, not in-memory                 |
|     - re-verifies evidence_bundle_hash before issuing a       |
|       permit, even after a human has approved                 |
|                                                               |
|  4. Permit Issuer     (app/security.py, app/permits.py)       |
|     - RS256-signed JWT, single-use nonce, short TTL           |
|     - binds: action, resource, parameters_hash,                |
|       evidence_bundle_hash, metric_definition_hash,            |
|       dataset_snapshot_id, policy_bundle_hash, approval_id     |
|                                                               |
|  5. Receipt / Audit   (app/audit.py)                          |
|     - reconstructs the full decision trail from one action_id |
+-------------------------------+-----------------------------+
                                | signed permit
                                v
                     Protected Executor (app/executor.py)
                     - only component holding "write" access
                     - verifies signature, audience, expiry, nonce
                     - post-execution guardrail check -> automatic
                       rollback on breach
                                |
                                v
                     Feature-flag / rollout store
```

See `docs/ARCHITECTURE.md` for the component-level detail and
`docs/EVIDENCE_MODEL.md` for exactly what fields go into an evidence bundle and
why nothing is collapsed into a single "trust score."

---

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Build the real evidence source: seeds a small experiment dataset into
# DuckDB via dbt, runs the fact-table model, and runs dbt tests.
bash scripts/run_dbt.sh

# Start the API + dashboard
uvicorn app.main:app --reload
# Dashboard: http://127.0.0.1:8000/
# API docs:  http://127.0.0.1:8000/docs
```

In a second terminal, run the scripted walkthrough:

```bash
python scripts/demo.py
```

This proposes a small in-authority rollout (auto-permitted), a larger one that
requires human approval, approves and executes it, replays the used permit
(rejected), triggers an automatic rollback via a simulated guardrail breach, and
denies an action tied to an unapproved metric — printing the exact decision and
reasoning at every step.

Run the test suite:

```bash
pytest -v
```

21 tests covering the policy engine's decision branches, permit
signing/tamper/expiry/audience checks, and a full HTTP-level walkthrough
through the real FastAPI app (propose → approve → execute → replay-rejected →
audit-reconstruction).

---

## What I'd point to in an interview

**The bug that taught me the most while building this:** the evidence bundle
hash originally included `source_freshness_minutes`, a value that's a
continuous function of wall-clock time. That meant the hash changed on every
single read — including the few milliseconds between an agent proposing an
action and a human approving it — so the "has evidence changed since approval"
check I'd built to catch stale approvals was tripping on *every* approval, not
just genuinely stale ones. The fix was separating what identifies evidence
(the dbt run, the dataset snapshot, the test results — things that only change
when the underlying data actually changes) from what gates it live (freshness
against a policy threshold, checked fresh on every evaluation, never hashed).
That's a distinction I hadn't thought about clearly before hitting it as a
failing test. `tests/test_end_to_end.py` and the freshness-handling code in
`app/evidence.py` reflect the fixed version; the reasoning is in a comment
directly above `bundle_hash`.

**The other one:** RSA-signed JWT `exp` claims computed from
`datetime.utcnow().timestamp()` are silently wrong on any host that isn't in
UTC, because `.timestamp()` on a naive datetime assumes *local* time. A permit
issued with a 1-second TTL didn't expire for five hours on this sandbox
(UTC-5). Caught by `tests/test_permits.py::test_expired_permit_is_rejected`
failing, not by inspection — which is the actual argument for writing the test
in the first place.

---

## Repository layout

```
app/                  FastAPI application
  main.py             app wiring, dashboard mount, /health, /metrics
  config.py           environment-driven configuration
  models.py            SQLAlchemy models (agents, actions, evidence, decisions,
                        approvals, permits, receipts)
  evidence.py          evidence broker (dbt artifacts + metric registry + guardrails)
  policy.py             deterministic rule engine
  security.py           RSA keypair mgmt, permit signing/verification
  permits.py             permit issuance + single-use consumption
  approvals.py            durable approval state machine
  executor.py              protected executor + guardrail rollback
  audit.py                  decision-trail reconstruction
  metrics.py                 Prometheus counters
  routers/                    HTTP endpoints
policies/               declarative policy rules (YAML)
config/                 agent registry + metric registry
dbt_project/            real dbt Core + DuckDB project (evidence source)
frontend/               single-page operator dashboard (vanilla JS)
scripts/
  run_dbt.sh             refresh dbt evidence artifacts
  demo.py                 scripted end-to-end walkthrough
tests/                  pytest suite (21 tests)
docs/
  ARCHITECTURE.md         component-level design notes
  EVIDENCE_MODEL.md        evidence bundle schema + rationale
  ORIGINAL_DESIGN.md        the original full-enterprise-stack concept
ROADMAP.md              production upgrade path for every simplification above
```

## Tech stack

Python, FastAPI, SQLAlchemy, PostgreSQL-ready (SQLite for local/demo), dbt Core,
DuckDB, PyJWT + `cryptography` (RS256 signed permits), PyYAML (policy + config),
Prometheus client, pytest, vanilla HTML/JS dashboard.
