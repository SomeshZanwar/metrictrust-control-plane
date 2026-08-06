"""Receipt / decision reconstruction.

Given an action_id, rebuild the full decision trail: what evidence was
used, what policy fired, who approved (if anyone), what permit was issued,
and what the executor actually did. This is what makes the answer to
"who or what authorized this?" a reconstructible fact instead of a log
line someone has to trust.
"""
import json
from sqlalchemy.orm import Session
from app.models import ActionRequest


def reconstruct_decision(db: Session, action_id: str) -> dict:
    action = db.query(ActionRequest).filter(ActionRequest.id == action_id).first()
    if action is None:
        return {}

    out = {
        "action_id": action.id,
        "agent_id": action.agent_id,
        "action_type": action.action_type,
        "resource": action.resource,
        "parameters": json.loads(action.parameters_json),
        "status": action.status,
        "created_at": action.created_at.isoformat(),
    }
    if action.evidence_bundle:
        out["evidence"] = json.loads(action.evidence_bundle.raw_json)
        out["evidence_bundle_hash"] = action.evidence_bundle.bundle_hash
    if action.decision:
        out["policy_decision"] = {
            "decision": action.decision.decision,
            "matched_rule": action.decision.matched_rule,
            "denial_reason": action.decision.denial_reason,
            "policy_bundle_hash": action.decision.policy_bundle_hash,
        }
    if action.approval:
        out["approval"] = {
            "id": action.approval.id,
            "status": action.approval.status,
            "approver_identity": action.approval.approver_identity,
            "approver_role": action.approval.approver_role,
            "evidence_bundle_hash_at_request": action.approval.evidence_bundle_hash_at_request,
            "requested_at": action.approval.requested_at.isoformat(),
            "decided_at": action.approval.decided_at.isoformat() if action.approval.decided_at else None,
        }
    if action.permit:
        out["permit"] = {
            "id": action.permit.id,
            "nonce": action.permit.nonce,
            "consumed": action.permit.consumed,
            "issued_at": action.permit.issued_at.isoformat(),
            "expires_at": action.permit.expires_at.isoformat(),
        }
    if action.receipt:
        out["receipt"] = {
            "id": action.receipt.id,
            "executor_result": action.receipt.executor_result,
            "detail": json.loads(action.receipt.detail_json),
            "created_at": action.receipt.created_at.isoformat(),
        }
    return out
