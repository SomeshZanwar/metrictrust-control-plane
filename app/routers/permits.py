from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import executor as executor_module, metrics
from app.database import get_db
from app.models import ActionRequest
from app.schemas import ExecuteRequest

router = APIRouter(prefix="/execute", tags=["execution"])


@router.post("/{action_id}")
def execute(action_id: str, req: ExecuteRequest, db: Session = Depends(get_db)):
    action = db.query(ActionRequest).filter(ActionRequest.id == action_id).first()
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")

    try:
        receipt = executor_module.execute_permit(db, action, req.permit_token)
    except executor_module.ExecutionError as e:
        metrics.executions_total.labels(result="REJECTED").inc()
        raise HTTPException(status_code=403, detail=str(e))

    metrics.executions_total.labels(result=receipt.executor_result).inc()
    return {
        "receipt_id": receipt.id,
        "executor_result": receipt.executor_result,
        "action_status": action.status,
    }
