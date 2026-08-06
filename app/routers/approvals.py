import yaml
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import config, evidence as evidence_module, policy, permits as permits_module, approvals as approvals_module, metrics
from app.database import get_db
from app.models import Approval, ActionRequest
from app.schemas import ApprovalDecisionRequest
import json

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("")
def list_pending(db: Session = Depends(get_db)):
    rows = db.query(Approval).filter(Approval.status == "PENDING").all()
    return [
        {
            "approval_id": a.id,
            "action_id": a.action_id,
            "expires_at": a.expires_at.isoformat(),
            "requested_at": a.requested_at.isoformat(),
        }
        for a in rows
    ]


@router.post("/{approval_id}/decide")
def decide(approval_id: str, req: ApprovalDecisionRequest, approve: bool, db: Session = Depends(get_db)):
    approval = db.query(Approval).filter(Approval.id == approval_id).first()
    if approval is None:
        raise HTTPException(status_code=404, detail="approval not found")

    try:
        approval = approvals_module.decide_approval(
            db, approval, approve=approve,
            approver_identity=req.approver_identity, approver_role=req.approver_role,
        )
    except approvals_module.ApprovalError as e:
        raise HTTPException(status_code=409, detail=str(e))

    action = db.query(ActionRequest).filter(ActionRequest.id == approval.action_id).first()

    if not approve:
        action.status = "DENIED"
        db.commit()
        return {"approval_id": approval.id, "status": approval.status, "action_status": action.status}

    # --- Approval-binding re-check: evidence must be re-verified against
    # the SAME evidence bundle the approver reviewed before a permit is
    # issued. If the underlying data has moved on, this is the point where
    # a stale-approval exploit would be caught. ---
    agents_cfg = {a["id"]: a for a in yaml.safe_load(config.AGENTS_CONFIG_PATH.read_text())["agents"]}
    agent_cfg = agents_cfg[action.agent_id]
    authority = agent_cfg.get("authority", {}).get(action.action_type, {})

    experiment_id = action.resource.split("/", 1)[1] if "/" in action.resource else action.resource
    fresh_bundle = evidence_module.build_evidence_bundle(experiment_id=experiment_id, metric_id=action.metric_id)

    if fresh_bundle["bundle_hash"] != approval.evidence_bundle_hash_at_request:
        action.status = "REQUIRE_APPROVAL"
        db.commit()
        raise HTTPException(
            status_code=409,
            detail=(
                "Evidence changed since this approval was requested "
                f"(was {approval.evidence_bundle_hash_at_request[:16]}..., now "
                f"{fresh_bundle['bundle_hash'][:16]}...). Approval is stale; "
                "re-propose the action to get a fresh evidence bundle and approval."
            ),
        )

    decision = policy.evaluate(
        action_type=action.action_type, resource=action.resource,
        parameters=json.loads(action.parameters_json), evidence=fresh_bundle, agent_authority=authority,
    )
    if decision["decision"] == "DENY":
        action.status = "DENIED"
        db.commit()
        raise HTTPException(status_code=409, detail=f"Re-evaluation denied the action: {decision['denial_reason']}")

    action.status = "APPROVED"
    db.commit()
    permit = permits_module.issue_permit_for_action(db, action, approval_id=approval.id)
    metrics.permits_issued_total.inc()

    return {
        "approval_id": approval.id,
        "status": approval.status,
        "action_status": action.status,
        "permit_id": permit.id,
        "permit_token": permit.token,
        "permit_expires_at": permit.expires_at.isoformat(),
    }
