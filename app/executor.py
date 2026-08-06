"""Protected Executor.

This is the only component holding "credentials" to mutate the target
system (here: a mock feature-flag / experiment-rollout store standing in
for OpenFeature + a real flag provider). It accepts nothing from the agent
directly — only a verified MetricTrust permit. If permit verification
fails for any reason, no mutation happens.

Also implements the post-execution guardrail check + automatic rollback
described in the design doc's circuit-breaker section, synchronously for
the demo (production would run this as a continuous background monitor).
"""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app import config, permits as permits_module
from app.evidence import _load_guardrails  # reuse the same simulated guardrail feed
from app.models import ActionRequest, Receipt

FLAG_STORE_PATH = config.EVIDENCE_STORE_DIR / "feature_flag_store.json"


def _load_store() -> dict:
    if FLAG_STORE_PATH.exists():
        return json.loads(FLAG_STORE_PATH.read_text())
    return {}


def _save_store(store: dict) -> None:
    config.EVIDENCE_STORE_DIR.mkdir(parents=True, exist_ok=True)
    FLAG_STORE_PATH.write_text(json.dumps(store, indent=2))


class ExecutionError(Exception):
    pass


def execute_permit(db: Session, action: ActionRequest, token: str) -> Receipt:
    try:
        claims = permits_module.verify_and_consume_permit(db, token)
    except permits_module.PermitConsumptionError as e:
        raise ExecutionError(str(e)) from e

    if claims["action"] != action.action_type or claims["resource"] != action.resource:
        raise ExecutionError("permit action/resource does not match the action being executed")

    store = _load_store()
    previous_value = store.get(action.resource, {}).get("rollout_percentage")
    requested = json.loads(action.parameters_json).get("requested_percentage")

    store[action.resource] = {
        "rollout_percentage": requested,
        "previous_rollout_percentage": previous_value,
        "updated_at": datetime.utcnow().isoformat(),
        "permit_id_used": claims["nonce"],
    }
    _save_store(store)

    # Post-execution guardrail check -> automatic rollback on breach.
    guardrails = _load_guardrails()
    executor_result = "SUCCESS"
    rollback_detail = None
    if guardrails.get("state") == "FAIL":
        store[action.resource]["rollout_percentage"] = previous_value
        store[action.resource]["rolled_back_at"] = datetime.utcnow().isoformat()
        _save_store(store)
        executor_result = "ROLLED_BACK"
        rollback_detail = guardrails

    action.status = "EXECUTED" if executor_result == "SUCCESS" else "ROLLED_BACK"

    receipt = Receipt(
        action_id=action.id,
        executor_result=executor_result,
        detail_json=json.dumps({
            "permit_nonce": claims["nonce"],
            "previous_value": previous_value,
            "new_value": store[action.resource]["rollout_percentage"],
            "requested_value": requested,
            "guardrail_check": guardrails,
            "rollback": rollback_detail,
        }),
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return receipt
