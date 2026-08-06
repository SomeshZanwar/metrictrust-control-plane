"""SQLAlchemy ORM models for the MetricTrust control plane state store.

In production this maps to PostgreSQL. SQLite is used for local/dev/demo
so the project runs with zero external services.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


class ActionRequest(Base):
    """A proposed business-changing action submitted by an agent."""
    __tablename__ = "action_requests"

    id = Column(String, primary_key=True, default=lambda: new_id("act"))
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False)
    action_type = Column(String, nullable=False)          # e.g. update_experiment_rollout
    resource = Column(String, nullable=False)              # e.g. experiment/onboarding-v4
    parameters_json = Column(Text, nullable=False)         # raw JSON parameters
    parameters_hash = Column(String, nullable=False)
    metric_id = Column(String, nullable=True)
    reason = Column(Text, nullable=True)
    risk_tier = Column(String, nullable=False, default="L2")
    status = Column(String, nullable=False, default="EVALUATING")
    # EVALUATING | DENIED | REQUIRE_APPROVAL | APPROVED | PERMIT_ISSUED | EXECUTED | ROLLED_BACK | EXPIRED
    created_at = Column(DateTime, default=datetime.utcnow)

    agent = relationship("Agent", back_populates="actions")
    evidence_bundle = relationship("EvidenceBundle", back_populates="action", uselist=False)
    decision = relationship("PolicyDecision", back_populates="action", uselist=False)
    approval = relationship("Approval", back_populates="action", uselist=False)
    permit = relationship("Permit", back_populates="action", uselist=False)
    receipt = relationship("Receipt", back_populates="action", uselist=False)


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    owner = Column(String, nullable=False)
    group = Column(String, nullable=False, default="default")
    api_key_hash = Column(String, nullable=False)
    active = Column(Boolean, default=True)

    actions = relationship("ActionRequest", back_populates="agent")


class EvidenceBundle(Base):
    """A structured, hashable snapshot of the evidence used to evaluate one action."""
    __tablename__ = "evidence_bundles"

    id = Column(String, primary_key=True, default=lambda: new_id("ev"))
    action_id = Column(String, ForeignKey("action_requests.id"), nullable=False)
    dbt_invocation_id = Column(String, nullable=True)
    manifest_hash = Column(String, nullable=True)
    run_results_hash = Column(String, nullable=True)
    critical_tests_failed = Column(Integer, default=0)
    source_freshness_minutes = Column(Float, nullable=True)
    assignment_integrity_test = Column(String, nullable=True)   # PASS | FAIL | UNKNOWN
    guardrail_state = Column(String, nullable=True)             # PASS | FAIL | UNKNOWN
    metric_approval_status = Column(String, nullable=True)      # APPROVED | UNAPPROVED
    metric_definition_hash = Column(String, nullable=True)
    dataset_snapshot_id = Column(String, nullable=True)
    lineage_closure_hash = Column(String, nullable=True)
    bundle_hash = Column(String, nullable=False)
    valid_until = Column(DateTime, nullable=False)
    raw_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    action = relationship("ActionRequest", back_populates="evidence_bundle")


class PolicyDecision(Base):
    __tablename__ = "policy_decisions"

    id = Column(String, primary_key=True, default=lambda: new_id("dec"))
    action_id = Column(String, ForeignKey("action_requests.id"), nullable=False)
    decision = Column(String, nullable=False)   # DENY | REQUIRE_APPROVAL | PERMIT
    matched_rule = Column(String, nullable=True)
    denial_reason = Column(Text, nullable=True)
    policy_bundle_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    action = relationship("ActionRequest", back_populates="decision")


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(String, primary_key=True, default=lambda: new_id("appr"))
    action_id = Column(String, ForeignKey("action_requests.id"), nullable=False)
    status = Column(String, nullable=False, default="PENDING")  # PENDING | APPROVED | DENIED | EXPIRED
    approver_identity = Column(String, nullable=True)
    approver_role = Column(String, nullable=True)
    evidence_bundle_hash_at_request = Column(String, nullable=False)
    requested_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)

    action = relationship("ActionRequest", back_populates="approval")


class Permit(Base):
    __tablename__ = "permits"

    id = Column(String, primary_key=True, default=lambda: new_id("permit"))
    action_id = Column(String, ForeignKey("action_requests.id"), nullable=False)
    token = Column(Text, nullable=False)
    nonce = Column(String, nullable=False, unique=True)
    consumed = Column(Boolean, default=False)
    issued_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    action = relationship("ActionRequest", back_populates="permit")


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(String, primary_key=True, default=lambda: new_id("rcpt"))
    action_id = Column(String, ForeignKey("action_requests.id"), nullable=False)
    executor_result = Column(String, nullable=False)   # SUCCESS | FAILED | ROLLED_BACK
    detail_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    action = relationship("ActionRequest", back_populates="receipt")
