"""Unit tests for the deterministic policy engine (app/policy.py).

These exercise the same four branches demonstrated in scripts/demo.py:
autonomous permit, require-approval fallback, hard-ceiling deny, and
evidence-based deny — plus the fail-closed default and policy-bundle
hash stability.
"""
from app import policy

GOOD_EVIDENCE = dict(
    source_freshness_minutes=10,
    metric_approval_status="APPROVED",
    assignment_integrity_test="PASS",
    critical_tests_failed=0,
    guardrail_state="PASS",
)
AUTHORITY = dict(autonomous_max_percentage=25, approval_max_percentage=50, prohibited_above_percentage=50)


def _evaluate(pct, evidence=None, authority=None):
    return policy.evaluate(
        action_type="update_experiment_rollout",
        resource="experiment/onboarding-v4",
        parameters={"requested_percentage": pct},
        evidence=evidence or GOOD_EVIDENCE,
        agent_authority=authority or AUTHORITY,
    )


def test_within_autonomy_is_permitted():
    r = _evaluate(20)
    assert r["decision"] == "PERMIT"
    assert r["matched_rule"] == "bounded_autonomy"


def test_above_autonomy_within_ceiling_requires_approval():
    r = _evaluate(50)
    assert r["decision"] == "REQUIRE_APPROVAL"
    assert r["matched_rule"] is None


def test_above_hard_ceiling_is_denied_even_though_no_approval_was_attempted():
    r = _evaluate(75)
    assert r["decision"] == "DENY"
    assert r["matched_rule"] == "approval_ceiling"


def test_failed_assignment_integrity_denies_regardless_of_requested_percentage():
    bad = dict(GOOD_EVIDENCE, assignment_integrity_test="FAIL")
    r = _evaluate(10, evidence=bad)
    assert r["decision"] == "DENY"
    assert r["matched_rule"] == "assignment_integrity"


def test_stale_source_denies():
    bad = dict(GOOD_EVIDENCE, source_freshness_minutes=999)
    r = _evaluate(10, evidence=bad)
    assert r["decision"] == "DENY"
    assert r["matched_rule"] == "stale_source"


def test_unapproved_metric_denies():
    bad = dict(GOOD_EVIDENCE, metric_approval_status="UNAPPROVED")
    r = _evaluate(10, evidence=bad)
    assert r["decision"] == "DENY"
    assert r["matched_rule"] == "unapproved_metric"


def test_failing_critical_dbt_tests_denies():
    bad = dict(GOOD_EVIDENCE, critical_tests_failed=2)
    r = _evaluate(10, evidence=bad)
    assert r["decision"] == "DENY"
    assert r["matched_rule"] == "critical_tests_passing"


def test_guardrail_breach_denies():
    bad = dict(GOOD_EVIDENCE, guardrail_state="FAIL")
    r = _evaluate(10, evidence=bad)
    assert r["decision"] == "DENY"
    assert r["matched_rule"] == "guardrail_state"


def test_unknown_action_type_with_no_matching_permit_rule_fails_closed():
    r = policy.evaluate(
        action_type="pause_experiment", resource="experiment/x",
        parameters={}, evidence=GOOD_EVIDENCE, agent_authority={},
    )
    assert r["decision"] == "REQUIRE_APPROVAL", "default must be ask-a-human, not allow"


def test_policy_bundle_hash_is_deterministic():
    assert policy.policy_bundle_hash() == policy.policy_bundle_hash()
