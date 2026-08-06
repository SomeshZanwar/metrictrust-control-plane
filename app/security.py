"""Key management and permit signing/verification.

Uses RS256-signed JWTs as evidence-bound execution permits. Keys are local
files for the demo; in production these would be KMS- or HSM-backed and
never touch application memory in plaintext.
"""
import json
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app import config


def ensure_keypair() -> None:
    config.KEYS_DIR.mkdir(parents=True, exist_ok=True)
    if config.PRIVATE_KEY_PATH.exists() and config.PUBLIC_KEY_PATH.exists():
        return
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    config.PRIVATE_KEY_PATH.write_bytes(private_bytes)
    config.PUBLIC_KEY_PATH.write_bytes(public_bytes)


def _private_key() -> str:
    return config.PRIVATE_KEY_PATH.read_text()


def _public_key() -> str:
    return config.PUBLIC_KEY_PATH.read_text()


def sha256_hex(data: str) -> str:
    return "sha256:" + hashlib.sha256(data.encode("utf-8")).hexdigest()


def canonical_hash(obj) -> str:
    """Deterministic hash of a JSON-serializable object (sorted keys, no whitespace)."""
    return sha256_hex(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str))


def issue_permit(
    *,
    subject: str,
    audience: str,
    action: str,
    resource: str,
    parameters_hash: str,
    evidence_bundle_hash: str,
    metric_definition_hash: str,
    dataset_snapshot_id: str,
    policy_bundle_hash: str,
    approval_id: str | None,
    risk_tier: str,
    ttl_seconds: int | None = None,
) -> tuple[str, str, datetime]:
    """Issue a signed, short-lived, single-use execution permit.

    Returns (token, nonce, expires_at).
    """
    ttl = ttl_seconds or config.PERMIT_TTL_SECONDS
    # Use timezone-aware UTC throughout: a naive datetime's .timestamp()
    # is interpreted as *local* time by Python, which silently produced
    # exp/iat claims offset by the host's UTC offset (caught by
    # tests/test_permits.py::test_expired_permit_is_rejected failing in a
    # non-UTC sandbox). Every other datetime in this project (SQLAlchemy
    # columns, evidence timestamps) stays naive-UTC by convention since
    # they never cross a .timestamp() boundary.
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl)
    nonce = secrets.token_hex(16)

    claims = {
        "iss": config.ISSUER,
        "sub": subject,
        "aud": audience,
        "action": action,
        "resource": resource,
        "parameters_hash": parameters_hash,
        "evidence_bundle_hash": evidence_bundle_hash,
        "metric_definition_hash": metric_definition_hash,
        "dataset_snapshot_id": dataset_snapshot_id,
        "policy_bundle_hash": policy_bundle_hash,
        "approval_id": approval_id,
        "risk_tier": risk_tier,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "nonce": nonce,
    }
    token = jwt.encode(claims, _private_key(), algorithm="RS256")
    return token, nonce, expires_at.replace(tzinfo=None)


class PermitVerificationError(Exception):
    pass


def decode_permit(token: str, *, expected_audience: str) -> dict:
    """Verify signature, expiry and audience. Raises PermitVerificationError on failure.

    Does NOT check nonce single-use — that is the caller's job, since it
    requires a database round-trip (see app/permits.py::consume_permit).
    """
    try:
        claims = jwt.decode(
            token,
            _public_key(),
            algorithms=["RS256"],
            audience=expected_audience,
            issuer=config.ISSUER,
        )
    except jwt.ExpiredSignatureError as e:
        raise PermitVerificationError("permit expired") from e
    except jwt.InvalidAudienceError as e:
        raise PermitVerificationError("permit audience mismatch") from e
    except jwt.InvalidTokenError as e:
        raise PermitVerificationError(f"invalid permit signature/claims: {e}") from e
    return claims
