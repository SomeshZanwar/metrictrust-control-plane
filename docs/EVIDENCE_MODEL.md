# Evidence model

Every proposed action gets one **Evidence Bundle** (`EvidenceBundle` in
`app/models.py`, built by `app/evidence.py`). The design rule is: expose
discrete, individually-checkable predicates, never collapse them into a
single composite "trust score." A score can average away one critical
failure; a set of named booleans and hashes cannot hide anything, and every
one of them is independently referenceable from a policy rule.

| Field | Source | Used by |
|---|---|---|
| `dbt_invocation_id` | `run_results.json["metadata"]["invocation_id"]` | audit trail (which dbt run produced this) |
| `manifest_hash` | hash of `manifest.json["metadata"]` | audit trail |
| `run_results_hash` | hash of `run_results.json["metadata"]` | audit trail |
| `critical_tests_failed` | count of non-`pass` results in `run_results.json` | `critical_tests_passing` policy rule |
| `source_freshness_minutes` | elapsed time since `run_results.json` was generated | `stale_source` policy rule — **live gate, excluded from `bundle_hash`** |
| `assignment_integrity_test` | result of the `assert_assignment_balance` singular dbt test | `assignment_integrity` policy rule |
| `guardrail_state` | live guardrail feed (`PASS`/`FAIL`) | `guardrail_state` policy rule + post-execution rollback check |
| `metric_approval_status` | `config/metrics_registry.yaml` lookup | `unapproved_metric` policy rule |
| `metric_definition_hash` | hash of the metric registry entry | bound into the issued permit |
| `dataset_snapshot_id` | hash of the exact rows read from `fct_experiment_outcomes` for this experiment | bound into the issued permit; this is what makes a permit specific to *this* data, not "data was fine at some point" |
| `lineage_closure_hash` | hash of a small lineage record (job, invocation id, upstream models/seed) | bound into the issued permit |
| `bundle_hash` | hash of every field above **except** `source_freshness_minutes` and `valid_until` | compared before issuing a permit after approval (approval-binding check) |

## Why `source_freshness_minutes` is excluded from `bundle_hash`

This was a real bug caught by a failing test, not a design decision made up
front (see the README's "what I'd point to in an interview" section for the
full story). Freshness is `(now - dbt_run_generated_at)` — it increases every
second by definition. Hashing it means the bundle hash changes on every
single read, which breaks the one thing the hash exists to do: let the
approval-binding check in `app/routers/approvals.py` tell "the same evidence,
re-read a few seconds later" apart from "the evidence actually changed." The
fix: freshness is still part of the evidence dict and still enforced by the
`stale_source` policy rule on every evaluation — it's just not part of what
identifies the bundle.

## What a permit actually binds

```json
{
  "sub": "agent:product-analytics-agent-01",
  "aud": "experiment-control-executor",
  "action": "update_experiment_rollout",
  "resource": "experiment/onboarding-v4",
  "parameters_hash": "sha256:...",
  "evidence_bundle_hash": "sha256:...",
  "metric_definition_hash": "sha256:...",
  "dataset_snapshot_id": "sha256:...",
  "policy_bundle_hash": "sha256:...",
  "approval_id": "appr_...",
  "risk_tier": "L3",
  "nonce": "single-use-value",
  "iat": 1234567890,
  "exp": 1234568490
}
```

Signed RS256. Verified by the executor for signature, issuer, audience, and
expiry (`app/security.py::decode_permit`), then checked against the database
for single-use consumption (`app/permits.py::verify_and_consume_permit`) —
a still-validly-signed, not-yet-expired permit is still rejected if it's
already been redeemed once.
