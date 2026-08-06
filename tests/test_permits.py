"""Tests for permit signing/verification (app/security.py) covering the
properties an execution-permit system actually has to hold: valid permits
verify, tampered permits are rejected, expired permits are rejected, and
audience mismatch is rejected. Single-use/replay is covered at the
persistence layer in test_end_to_end.py since it requires the DB.
"""
import time

import pytest

from app import security

security.ensure_keypair()


def _issue(**overrides):
    kwargs = dict(
        subject="agent:test-agent",
        audience="experiment-control-executor",
        action="update_experiment_rollout",
        resource="experiment/onboarding-v4",
        parameters_hash="sha256:abc",
        evidence_bundle_hash="sha256:def",
        metric_definition_hash="sha256:ghi",
        dataset_snapshot_id="sha256:jkl",
        policy_bundle_hash="sha256:mno",
        approval_id=None,
        risk_tier="L3",
    )
    kwargs.update(overrides)
    return security.issue_permit(**kwargs)


def test_valid_permit_round_trips():
    token, nonce, expires_at = _issue()
    claims = security.decode_permit(token, expected_audience="experiment-control-executor")
    assert claims["nonce"] == nonce
    assert claims["action"] == "update_experiment_rollout"
    assert claims["evidence_bundle_hash"] == "sha256:def"


def test_tampered_token_is_rejected():
    token, _, _ = _issue()
    # Flip a character in the payload segment — signature must fail.
    parts = token.split(".")
    payload = list(parts[1])
    payload[5] = "A" if payload[5] != "A" else "B"
    parts[1] = "".join(payload)
    tampered = ".".join(parts)
    with pytest.raises(security.PermitVerificationError):
        security.decode_permit(tampered, expected_audience="experiment-control-executor")


def test_expired_permit_is_rejected():
    token, _, _ = _issue(ttl_seconds=1)
    time.sleep(2)
    with pytest.raises(security.PermitVerificationError):
        security.decode_permit(token, expected_audience="experiment-control-executor")


def test_audience_mismatch_is_rejected():
    token, _, _ = _issue()
    with pytest.raises(security.PermitVerificationError):
        security.decode_permit(token, expected_audience="some-other-service")


def test_bundle_hash_is_bound_into_the_permit():
    token, _, _ = _issue(evidence_bundle_hash="sha256:specific-evidence")
    claims = security.decode_permit(token, expected_audience="experiment-control-executor")
    assert claims["evidence_bundle_hash"] == "sha256:specific-evidence"
