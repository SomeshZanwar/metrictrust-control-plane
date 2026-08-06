import yaml
from fastapi import APIRouter
from app import config

router = APIRouter(tags=["registry"])


@router.get("/agents")
def list_agents():
    agents = yaml.safe_load(config.AGENTS_CONFIG_PATH.read_text())["agents"]
    return [{k: v for k, v in a.items() if k != "api_key"} for a in agents]


@router.get("/policies")
def list_policies():
    from app import policy
    rules = policy.load_policies()
    return {"policy_bundle_hash": policy.policy_bundle_hash(rules), "rules": rules}


@router.get("/flags")
def list_flags():
    from app import executor as executor_module
    return executor_module._load_store()
