"""Permit lifecycle: issue, verify, consume (single-use enforcement)."""
from datetime import datetime

from sqlalchemy.orm import Session

from app import config, security
from app.models import Permit, ActionRequest


EXECUTOR_AUDIENCE = "experiment-control-executor"


def issue_permit_for_action(db: Session, action: ActionRequest, *, approval_id: str | None) -> Permit:
    evidence = action.evidence_bundle
    decision = action.decision
    token, nonce, expires_at = security.issue_permit(
        subject=f"agent:{action.agent_id}",
        audience=EXECUTOR_AUDIENCE,
        action=action.action_type,
        resource=action.resource,
        parameters_hash=action.parameters_hash,
        evidence_bundle_hash=evidence.bundle_hash,
        metric_definition_hash=evidence.metric_definition_hash or "",
        dataset_snapshot_id=evidence.dataset_snapshot_id or "",
        policy_bundle_hash=decision.policy_bundle_hash,
        approval_id=approval_id,
        risk_tier=action.risk_tier,
    )
    permit = Permit(action_id=action.id, token=token, nonce=nonce, expires_at=expires_at)
    db.add(permit)
    action.status = "PERMIT_ISSUED"
    db.commit()
    db.refresh(permit)
    return permit


class PermitConsumptionError(Exception):
    pass


def verify_and_consume_permit(db: Session, token: str) -> dict:
    """Full executor-side verification: signature, audience, expiry,
    issuer (via security.decode_permit), then single-use nonce
    consumption against the database — replay of an already-used permit
    is rejected even if the signature and expiry are still technically
    valid.
    """
    try:
        claims = security.decode_permit(token, expected_audience=EXECUTOR_AUDIENCE)
    except security.PermitVerificationError as e:
        raise PermitConsumptionError(str(e)) from e

    permit = db.query(Permit).filter(Permit.nonce == claims["nonce"]).first()
    if permit is None:
        raise PermitConsumptionError("permit not found in issuance record (possible forgery)")
    if permit.consumed:
        raise PermitConsumptionError("permit already consumed (replay rejected)")
    if permit.expires_at < datetime.utcnow():
        raise PermitConsumptionError("permit expired")

    permit.consumed = True
    db.commit()
    return claims
