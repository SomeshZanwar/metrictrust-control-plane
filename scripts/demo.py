#!/usr/bin/env python3
"""End-to-end demo: replays the onboarding-v4 experiment-rollout scenario
from the design doc against a running MetricTrust API.

Run:
    uvicorn app.main:app --reload &
    python scripts/demo.py

Narrative:
  1. Agent proposes a small, in-authority rollout bump (10% -> 20%).
     Evidence passes every check -> PERMIT issued automatically, no human
     in the loop.
  2. Agent proposes a larger bump (20% -> 50%) based on a real activation-
     rate lift in the dbt-built fact table. This exceeds its autonomous
     ceiling -> REQUIRE_APPROVAL.
  3. A Product Owner approves. MetricTrust re-verifies the evidence bundle
     hasn't moved before issuing a permit (the "approval-binding" check).
  4. The permit is redeemed exactly once against the protected executor,
     which is the only component holding "credentials" to the feature-flag
     store.
  5. A live guardrail feed flips to FAIL after a further rollout — the
     executor's post-execution check catches it and automatically rolls
     the flag back, without any human action.
  6. Replaying an already-used permit is rejected.
  7. Proposing an action on an unapproved metric is denied outright.

Every step below prints the exact HTTP call and the exact decision
MetricTrust made and why — this is the "reconstructible evidence trail"
the project is built around.
"""
import json
import sys
import time
from pathlib import Path

import httpx

_client = httpx.Client(trust_env=False, timeout=10)

BASE = "http://127.0.0.1:8000"
AGENT_ID = "product-analytics-agent-01"
API_KEY = "demo-key-product-analytics-01"
RESOURCE = "experiment/onboarding-v4"
GUARDRAILS_PATH = Path(__file__).resolve().parent.parent / "evidence_store" / "guardrails.json"
FLAG_STORE_PATH = Path(__file__).resolve().parent.parent / "evidence_store" / "feature_flag_store.json"


def hr(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def set_guardrails(state: str) -> None:
    GUARDRAILS_PATH.write_text(json.dumps({
        "state": state,
        "checked_at": "demo",
        "error_rate_change": 0.031 if state == "FAIL" else 0.001,
    }))


def propose(current: int, requested: int, metric_id: str = "seven_day_activation_rate", reason: str = "") -> dict:
    r = _client.post(f"{BASE}/actions/propose", json={
        "agent_id": AGENT_ID, "api_key": API_KEY,
        "action_type": "update_experiment_rollout", "resource": RESOURCE,
        "parameters": {"current_percentage": current, "requested_percentage": requested},
        "metric_id": metric_id, "reason": reason,
    })
    print(f"POST /actions/propose  {current}% -> {requested}%  (metric={metric_id})")
    print(json.dumps(r.json(), indent=2)[:800])
    return r.json()


def main() -> None:
    if FLAG_STORE_PATH.exists():
        FLAG_STORE_PATH.unlink()
    set_guardrails("PASS")

    try:
        _client.get(f"{BASE}/health", timeout=2)
    except httpx.ConnectError:
        print("MetricTrust API is not running. Start it first:\n"
              "  uvicorn app.main:app --reload\n", file=sys.stderr)
        sys.exit(1)

    hr("STEP 1 — In-authority rollout bump: 10% -> 20% (expect autonomous PERMIT)")
    r1 = propose(10, 20, reason="small bump, within autonomous ceiling")
    assert r1["decision"] == "PERMIT"

    hr("STEP 2 — Larger bump based on real lift: 20% -> 50% (expect REQUIRE_APPROVAL)")
    r2 = propose(20, 50, reason="Treatment activation rate beats control in fct_experiment_outcomes")
    assert r2["decision"] == "REQUIRE_APPROVAL"
    approval_id = r2["approval_id"]
    action_id = r2["action_id"]

    hr("STEP 3 — Product Owner approves (evidence re-verified before permit issuance)")
    r3 = _client.post(f"{BASE}/approvals/{approval_id}/decide", params={"approve": "true"},
                     json={"approver_identity": "pm@example.com", "approver_role": "product_owner"})
    print(json.dumps(r3.json(), indent=2)[:600])
    r3j = r3.json()
    assert r3.status_code == 200, r3j
    permit_token = r3j["permit_token"]

    hr("STEP 4 — Protected executor redeems the permit exactly once")
    r4 = _client.post(f"{BASE}/execute/{action_id}", json={"permit_token": permit_token})
    print(json.dumps(r4.json(), indent=2))
    assert r4.json()["executor_result"] == "SUCCESS"

    hr("STEP 5 — Replay the same permit (expect 403, single-use enforced)")
    r5 = _client.post(f"{BASE}/execute/{action_id}", json={"permit_token": permit_token})
    print(f"HTTP {r5.status_code}: {r5.json()}")
    assert r5.status_code == 403

    hr("STEP 6 — Further rollout, but a live guardrail breach triggers automatic rollback")
    r6 = propose(50, 75, reason="continuing the rollout")
    # 75% exceeds the approval_max_percentage ceiling (50) -> denied outright
    print(f"\n(75% exceeds this agent's hard ceiling, so it is denied before guardrails even matter: "
          f"{r6['decision']} / {r6['matched_rule']})")

    r6b = propose(20, 25, reason="modest bump, still autonomous")
    permit_token_2 = r6b["permit_token"]
    print("\nSimulating a guardrail breach (error rate spike) after this permit is issued...")
    set_guardrails("FAIL")
    r7 = _client.post(f"{BASE}/execute/{r6b['action_id']}", json={"permit_token": permit_token_2})
    print(json.dumps(r7.json(), indent=2))
    assert r7.json()["executor_result"] == "ROLLED_BACK"
    set_guardrails("PASS")

    hr("STEP 7 — Deny outright: action tied to an unapproved metric")
    r8 = propose(20, 25, metric_id="experimental_unvetted_metric", reason="bad metric")
    print(f"\ndecision={r8['decision']} matched_rule={r8['matched_rule']}")
    assert r8["decision"] == "DENY"

    hr("STEP 8 — Full reconstructed decision trail for the executed action")
    r9 = _client.get(f"{BASE}/actions/{action_id}")
    print(json.dumps(r9.json(), indent=2))

    hr("DEMO COMPLETE — every decision above is reconstructible from GET /actions/{id}")


if __name__ == "__main__":
    main()
