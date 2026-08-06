from typing import Optional, Any
from pydantic import BaseModel


class ActionProposeRequest(BaseModel):
    agent_id: str
    api_key: str
    action_type: str
    resource: str
    parameters: dict[str, Any]
    metric_id: Optional[str] = None
    reason: Optional[str] = None


class ApprovalDecisionRequest(BaseModel):
    approver_identity: str
    approver_role: str = "product_owner"


class ExecuteRequest(BaseModel):
    permit_token: str
