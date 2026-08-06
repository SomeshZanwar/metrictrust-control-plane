"""Full-stack test through the real FastAPI app, real dbt-produced
evidence artifacts, and a real signed permit — the same path
scripts/demo.py exercises manually. Requires dbt_project/target/*.json
and the DuckDB file to already exist (run scripts/run_dbt.sh once before
running this file, exactly as the README instructs).
"""
import pytest
from fastapi.testclient import TestClient

from app import config

pytestmark = pytest.mark.skipif(
    not (config.DBT_TARGET_DIR / "run_results.json").exists(),
    reason="dbt artifacts not built yet — run scripts/run_dbt.sh first",
)

from app.main import app  # noqa: E402  (import after skip check / env setup)

client = TestClient(app)

AGENT = {"agent_id": "product-analytics-agent-01", "api_key": "demo-key-product-analytics-01"}


def propose(current, requested, metric_id="seven_day_activation_rate"):
    return client.post("/actions/propose", json={
        **AGENT,
        "action_type": "update_experiment_rollout",
        "resource": "experiment/onboarding-v4",
        "parameters": {"current_percentage": current, "requested_percentage": requested},
        "metric_id": metric_id,
        "reason": "test",
    })


def test_health():
    assert client.get("/health").status_code == 200


def test_autonomous_action_gets_permit_immediately():
    r = propose(10, 20)
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "PERMIT"
    assert "permit_token" in body


def test_over_ceiling_requires_approval_then_executes():
    r = propose(20, 50)
    body = r.json()
    assert body["decision"] == "REQUIRE_APPROVAL"

    approve = client.post(
        f"/approvals/{body['approval_id']}/decide", params={"approve": "true"},
        json={"approver_identity": "pm@example.com", "approver_role": "product_owner"},
    )
    assert approve.status_code == 200, approve.text
    permit_token = approve.json()["permit_token"]

    exec1 = client.post(f"/execute/{body['action_id']}", json={"permit_token": permit_token})
    assert exec1.status_code == 200
    assert exec1.json()["executor_result"] == "SUCCESS"

    # Replaying the same permit must be rejected even though the token
    # itself is still validly signed and not yet time-expired.
    exec2 = client.post(f"/execute/{body['action_id']}", json={"permit_token": permit_token})
    assert exec2.status_code == 403
    assert "replay" in exec2.json()["detail"] or "consumed" in exec2.json()["detail"]


def test_unapproved_metric_is_denied():
    r = propose(10, 15, metric_id="experimental_unvetted_metric")
    assert r.json()["decision"] == "DENY"
    assert r.json()["matched_rule"] == "unapproved_metric"


def test_forged_permit_token_is_rejected_by_executor():
    r = propose(10, 20)
    action_id = r.json()["action_id"]
    forged = r.json()["permit_token"][:-5] + "AAAAA"
    resp = client.post(f"/execute/{action_id}", json={"permit_token": forged})
    assert resp.status_code == 403


def test_audit_trail_is_reconstructible():
    r = propose(10, 20)
    action_id = r.json()["action_id"]
    audit = client.get(f"/actions/{action_id}")
    assert audit.status_code == 200
    body = audit.json()
    assert body["evidence_bundle_hash"] == body["evidence"]["bundle_hash"]
    assert body["policy_decision"]["decision"] == "PERMIT"
