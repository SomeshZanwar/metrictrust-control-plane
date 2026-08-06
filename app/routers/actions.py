import hashlib
import json
import time

import yaml
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from datetime import datetime
from app import config, evidence as evidence_module, policy, permits as permits_module, approvals as approvals_module, metrics
from app.database import get_db
from app.models import Agent, ActionRequest, EvidenceBundle, PolicyDecision
from app.schemas import ActionProposeRequest

router = APIRouter(prefix="/actions", tags=["actions"])


def _load_agents_config() -> dict:
    return yaml.safe_load(config.AGENTS_CONFIG_PATH.read_text())["agents"]


def _get_agent_authority(agent_cfg: dict, action_type: str) -> dict:
    return agent_cfg.get("authority", {}).get(action_type, {})


def _hash_params(params: dict) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(params, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _resource_experiment_id(resource: str) -> str:
    # resource is of the form "experiment/<id>"
    return resource.split("/", 1)[1] if "/" in resource else resource


@router.post("/propose")
def propose_action(req: ActionProposeRequest, db: Session = Depends(get_db)):
    with metrics.decision_latency_seconds.time():
        agents_cfg = {a["id"]: a for a in _load_agents_config()}
        agent_cfg = agents_cfg.get(req.agent_id)
        if agent_cfg is None or agent_cfg["api_key"] != req.api_key:
            raise HTTPException(status_code=401, detail="unknown agent or invalid api key")

        agent = db.query(Agent).filter(Agent.id == req.agent_id).first()
        if agent is None:
            agent = Agent(
                id=req.agent_id,
                display_name=agent_cfg["display_name"],
                owner=agent_cfg["owner"],
                group=agent_cfg["group"],
                api_key_hash=hashlib.sha256(req.api_key.encode()).hexdigest(),
            )
            db.add(agent)
            db.commit()

        action = ActionRequest(
            agent_id=agent.id,
            action_type=req.action_type,
            resource=req.resource,
            parameters_json=json.dumps(req.parameters),
            parameters_hash=_hash_params(req.parameters),
            metric_id=req.metric_id,
            reason=req.reason,
            risk_tier="L3",
            status="EVALUATING",
        )
        db.add(action)
        db.commit()
        db.refresh(action)

        try:
            experiment_id = _resource_experiment_id(req.resource)
            bundle = evidence_module.build_evidence_bundle(
                experiment_id=experiment_id, metric_id=req.metric_id
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=412, detail=str(e))

        eb = EvidenceBundle(
            action_id=action.id,
            dbt_invocation_id=bundle["dbt_invocation_id"],
            manifest_hash=bundle["manifest_hash"],
            run_results_hash=bundle["run_results_hash"],
            critical_tests_failed=bundle["critical_tests_failed"],
            source_freshness_minutes=bundle["source_freshness_minutes"],
            assignment_integrity_test=bundle["assignment_integrity_test"],
            guardrail_state=bundle["guardrail_state"],
            metric_approval_status=bundle["metric_approval_status"],
            metric_definition_hash=bundle["metric_definition_hash"],
            dataset_snapshot_id=bundle["dataset_snapshot_id"],
            lineage_closure_hash=bundle["lineage_closure_hash"],
            bundle_hash=bundle["bundle_hash"],
            valid_until=datetime.fromisoformat(bundle["valid_until"]),
            raw_json=json.dumps(bundle, default=str),
        )
        db.add(eb)
        db.commit()
        db.refresh(eb)

        authority = _get_agent_authority(agent_cfg, req.action_type)
        decision = policy.evaluate(
            action_type=req.action_type,
            resource=req.resource,
            parameters=req.parameters,
            evidence=bundle,
            agent_authority=authority,
        )
        metrics.decisions_total.labels(decision=decision["decision"]).inc()

        pd = PolicyDecision(
            action_id=action.id,
            decision=decision["decision"],
            matched_rule=decision["matched_rule"],
            denial_reason=decision["denial_reason"],
            policy_bundle_hash=decision["policy_bundle_hash"],
        )
        db.add(pd)

        result = {"action_id": action.id, "decision": decision["decision"],
                  "matched_rule": decision["matched_rule"], "denial_reason": decision["denial_reason"]}

        if decision["decision"] == "DENY":
            action.status = "DENIED"
            db.commit()
        elif decision["decision"] == "REQUIRE_APPROVAL":
            action.status = "REQUIRE_APPROVAL"
            db.commit()
            approval = approvals_module.create_approval(db, action)
            result["approval_id"] = approval.id
        else:  # PERMIT — within bounded autonomy, no human approval needed
            action.status = "APPROVED"
            db.commit()
            permit = permits_module.issue_permit_for_action(db, action, approval_id=None)
            metrics.permits_issued_total.inc()
            result["permit_id"] = permit.id
            result["permit_token"] = permit.token
            result["permit_expires_at"] = permit.expires_at.isoformat()

        return result


@router.get("/{action_id}")
def get_action(action_id: str, db: Session = Depends(get_db)):
    from app.audit import reconstruct_decision
    out = reconstruct_decision(db, action_id)
    if not out:
        raise HTTPException(status_code=404, detail="action not found")
    return out


@router.get("")
def list_actions(db: Session = Depends(get_db)):
    actions = db.query(ActionRequest).order_by(ActionRequest.created_at.desc()).limit(100).all()
    return [
        {
            "action_id": a.id,
            "agent_id": a.agent_id,
            "action_type": a.action_type,
            "resource": a.resource,
            "status": a.status,
            "risk_tier": a.risk_tier,
            "created_at": a.created_at.isoformat(),
        }
        for a in actions
    ]
