"""Human-approval workflow.

A durable state machine (PENDING -> APPROVED/DENIED/EXPIRED) stored in the
database rather than in-memory, so a pending approval survives an API
restart. A dedicated workflow engine (Temporal) is the documented
production upgrade for retries/escalation/timeouts at scale — see
ROADMAP.md — but the state-machine contract here is API-compatible with
swapping the backing engine later.

The key correctness property, preserved from the original design: approval
of an action does NOT by itself authorize execution. Evidence is
re-verified against the SAME evidence_bundle_hash the approver saw before a
permit is issued (see routers/approvals.py). If the evidence bundle has
moved on, the approval is stale and the request must be re-evaluated.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import config
from app.models import Approval, ActionRequest


def create_approval(db: Session, action: ActionRequest) -> Approval:
    approval = Approval(
        action_id=action.id,
        status="PENDING",
        evidence_bundle_hash_at_request=action.evidence_bundle.bundle_hash,
        expires_at=datetime.utcnow() + timedelta(seconds=config.APPROVAL_TTL_SECONDS),
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


class ApprovalError(Exception):
    pass


def decide_approval(db: Session, approval: Approval, *, approve: bool,
                     approver_identity: str, approver_role: str) -> Approval:
    if approval.status != "PENDING":
        raise ApprovalError(f"approval is already {approval.status}, not PENDING")
    if approval.expires_at < datetime.utcnow():
        approval.status = "EXPIRED"
        db.commit()
        raise ApprovalError("approval window expired")

    approval.status = "APPROVED" if approve else "DENIED"
    approval.approver_identity = approver_identity
    approval.approver_role = approver_role
    approval.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(approval)
    return approval
