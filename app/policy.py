"""Deterministic policy engine.

Rules are declarative YAML (principal/action/resource/context model,
directly inspired by Cedar's forbid/permit structure) and are evaluated by
plain Python comparisons — no arbitrary code execution, no LLM in the
decision path. An LLM may explain *why* a decision was made; it never
makes the decision. See design note in README.md.

Decision algorithm (fail-closed):
  1. Any matching `forbid` rule => DENY.
  2. Else any matching `permit` rule => the action is within bounded
     autonomous authority => PERMIT.
  3. Else => REQUIRE_APPROVAL (default is "ask a human", not "allow").
"""
from pathlib import Path
from typing import Any

import yaml

from app import config, security

_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and b is not None and a > b,
    "gte": lambda a, b: a is not None and b is not None and a >= b,
    "lt": lambda a, b: a is not None and b is not None and a < b,
    "lte": lambda a, b: a is not None and b is not None and a <= b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
}


def _get_path(context: dict, path: str) -> Any:
    node = context
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def load_policies() -> list[dict]:
    rules = []
    for path in sorted(config.POLICIES_DIR.glob("*.yaml")):
        rule = yaml.safe_load(path.read_text(encoding="utf-8"))
        rule["_source_file"] = path.name
        rules.append(rule)
    return rules


def policy_bundle_hash(rules: list[dict] | None = None) -> str:
    rules = rules if rules is not None else load_policies()
    return security.canonical_hash(rules)


def _rule_matches(rule: dict, context: dict) -> bool:
    action_filter = rule.get("action", "*")
    if action_filter != "*" and action_filter != context.get("action"):
        return False
    for cond in rule.get("conditions", []):
        actual = _get_path(context, cond["path"])
        if "value_ref" in cond:
            expected = _get_path(context, cond["value_ref"])
        else:
            expected = cond.get("value")
        op = _OPS[cond["op"]]
        if not op(actual, expected):
            return False
    return True


def evaluate(*, action_type: str, resource: str, parameters: dict,
             evidence: dict, agent_authority: dict) -> dict:
    """Evaluate all policies against one proposed action.

    Returns {decision, matched_rule, denial_reason, policy_bundle_hash}
    where decision is DENY | REQUIRE_APPROVAL | PERMIT.
    """
    rules = load_policies()
    bundle_hash = policy_bundle_hash(rules)

    context = {
        "action": action_type,
        "resource": resource,
        "parameters": parameters,
        "evidence": evidence,
        "agent_authority": agent_authority,
    }

    for rule in rules:
        if rule.get("effect") == "forbid" and _rule_matches(rule, context):
            return {
                "decision": "DENY",
                "matched_rule": rule["id"],
                "denial_reason": rule.get("description", "").strip(),
                "policy_bundle_hash": bundle_hash,
            }

    for rule in rules:
        if rule.get("effect") == "permit" and _rule_matches(rule, context):
            return {
                "decision": "PERMIT",
                "matched_rule": rule["id"],
                "denial_reason": None,
                "policy_bundle_hash": bundle_hash,
            }

    return {
        "decision": "REQUIRE_APPROVAL",
        "matched_rule": None,
        "denial_reason": "No autonomous-authority rule matched; action requires human approval.",
        "policy_bundle_hash": bundle_hash,
    }
