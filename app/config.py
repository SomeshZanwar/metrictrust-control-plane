"""Central configuration. Reads from environment with sane local defaults."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/metrictrust.db")

PERMIT_TTL_SECONDS = int(os.getenv("PERMIT_TTL_SECONDS", "600"))
APPROVAL_TTL_SECONDS = int(os.getenv("APPROVAL_TTL_SECONDS", "14400"))
EVIDENCE_MAX_AGE_MINUTES = int(os.getenv("EVIDENCE_MAX_AGE_MINUTES", "60"))

KEYS_DIR = BASE_DIR / "keys"
PRIVATE_KEY_PATH = KEYS_DIR / "permit_signing_key.pem"
PUBLIC_KEY_PATH = KEYS_DIR / "permit_signing_key.pub"

POLICIES_DIR = BASE_DIR / "policies"
AGENTS_CONFIG_PATH = BASE_DIR / "config" / "agents.yaml"
METRICS_REGISTRY_PATH = BASE_DIR / "config" / "metrics_registry.yaml"

DBT_PROJECT_DIR = BASE_DIR / "dbt_project"
DBT_TARGET_DIR = DBT_PROJECT_DIR / "target"

EVIDENCE_STORE_DIR = BASE_DIR / "evidence_store"

ISSUER = "metrictrust-control-plane"
