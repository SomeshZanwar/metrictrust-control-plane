"""Evidence Broker.

Turns real dbt artifacts (manifest.json / run_results.json) plus a metric
registry and a guardrail feed into a structured, hashable Evidence Bundle.

Design choice: this module never collapses evidence into a single "trust
score". It exposes discrete, policy-readable predicates
(critical_tests_failed, assignment_integrity_test, metric_approval_status,
...) because a composite score is hard to audit and can hide a single
critical failure behind an average. See ROADMAP.md / project README for
the reasoning.
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import yaml

from app import config, security

RUN_RESULTS_PATH = config.DBT_TARGET_DIR / "run_results.json"
MANIFEST_PATH = config.DBT_TARGET_DIR / "manifest.json"
DUCKDB_PATH = config.BASE_DIR / "metrictrust_evidence.duckdb"
GUARDRAILS_PATH = config.EVIDENCE_STORE_DIR / "guardrails.json"


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run scripts/run_dbt.sh first to produce dbt artifacts."
        )
    return json.loads(path.read_text())


def _load_metric_registry() -> dict:
    return yaml.safe_load(config.METRICS_REGISTRY_PATH.read_text())["metrics"]


def _load_guardrails() -> dict:
    """Simulated guardrail feed (error rate / support contacts / payment
    failures). In production this is a live query against the same
    observability stack that powers circuit breakers. Kept as an editable
    JSON fixture here so the demo scenario can flip PASS -> FAIL
    deterministically. See scripts/demo.py.
    """
    if GUARDRAILS_PATH.exists():
        return json.loads(GUARDRAILS_PATH.read_text())
    return {"state": "PASS", "checked_at": datetime.utcnow().isoformat()}


def _dataset_snapshot(experiment_id: str) -> tuple[str, dict]:
    """Query the dbt-built fact table directly and hash the exact rows the
    decision will be based on. This is what makes the resulting permit
    bindable to 'this exact data', not just 'data was fine at some point'.
    """
    if not DUCKDB_PATH.exists():
        raise FileNotFoundError(f"{DUCKDB_PATH} not found. Run scripts/run_dbt.sh first.")
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        rows = con.execute(
            "select experiment_id, variant, users, activated_users, activation_rate, "
            "last_event_ts from main.fct_experiment_outcomes "
            "where experiment_id = ? order by variant",
            [experiment_id],
        ).fetchall()
        cols = [d[0] for d in con.description]
    finally:
        con.close()
    records = [dict(zip(cols, r)) for r in rows]
    snapshot_id = security.canonical_hash(records)
    return snapshot_id, {"experiment_id": experiment_id, "rows": records}


def build_evidence_bundle(*, experiment_id: str, metric_id: str | None) -> dict:
    """Build the full Decision Evidence Bundle for one proposed action.

    Returns a plain dict (not yet persisted) with a `bundle_hash` field
    computed over every other field, so any later mutation is detectable.
    """
    run_results = _load_json(RUN_RESULTS_PATH)
    manifest = _load_json(MANIFEST_PATH)

    manifest_hash = security.canonical_hash(manifest["metadata"])
    run_results_hash = security.canonical_hash(run_results["metadata"])
    invocation_id = run_results["metadata"].get("invocation_id")

    critical_tests_failed = sum(
        1 for r in run_results["results"]
        if r["unique_id"].startswith("test.") and r["status"] not in ("pass", "success")
    )

    assignment_test_result = next(
        (r for r in run_results["results"] if "assignment_balance" in r["unique_id"]),
        None,
    )
    assignment_integrity_test = (
        "PASS" if assignment_test_result and assignment_test_result["status"] == "pass"
        else "FAIL" if assignment_test_result
        else "UNKNOWN"
    )

    generated_at = run_results["metadata"].get("generated_at")
    if generated_at:
        gen_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00")).replace(tzinfo=None)
        source_freshness_minutes = max(0.0, (datetime.utcnow() - gen_dt).total_seconds() / 60)
    else:
        source_freshness_minutes = None

    metrics = _load_metric_registry()
    metric_entry = metrics.get(metric_id) if metric_id else None
    metric_approval_status = metric_entry["approval_status"] if metric_entry else "UNKNOWN"
    metric_definition_hash = (
        security.canonical_hash(metric_entry) if metric_entry else security.sha256_hex("unknown")
    )

    guardrails = _load_guardrails()

    dataset_snapshot_id, snapshot_payload = _dataset_snapshot(experiment_id)

    lineage_closure = {
        "job": "metrictrust_evidence.dbt_run",
        "invocation_id": invocation_id,
        "upstream_models": ["stg_experiment_events", "fct_experiment_outcomes"],
        "upstream_seed": "raw_experiment_events",
    }
    lineage_closure_hash = security.canonical_hash(lineage_closure)

    valid_until = datetime.utcnow() + timedelta(minutes=config.EVIDENCE_MAX_AGE_MINUTES)

    bundle = {
        "dbt_invocation_id": invocation_id,
        "manifest_hash": manifest_hash,
        "run_results_hash": run_results_hash,
        "critical_tests_failed": critical_tests_failed,
        "source_freshness_minutes": source_freshness_minutes,
        "assignment_integrity_test": assignment_integrity_test,
        "guardrail_state": guardrails.get("state", "UNKNOWN"),
        "metric_id": metric_id,
        "metric_approval_status": metric_approval_status,
        "metric_definition_hash": metric_definition_hash,
        "dataset_snapshot_id": dataset_snapshot_id,
        "dataset_snapshot": snapshot_payload,
        "lineage_closure_hash": lineage_closure_hash,
        "valid_until": valid_until.isoformat(),
    }

    # bundle_hash identifies the *substance* of the evidence (which dbt run,
    # which dataset snapshot, which test/guardrail/metric state) — not the
    # instant it happened to be read. `source_freshness_minutes` is a
    # continuously drifting clock value; hashing it would make the bundle
    # hash change on every single read even when nothing about the
    # underlying data changed, which would make every approval look
    # "stale" a few milliseconds after it was granted. Freshness is instead
    # enforced live, every time, via the stale_source policy rule — a
    # separate, deliberate design choice from what gets bound into the
    # permit's identity hash.
    hashable = {k: v for k, v in bundle.items() if k not in ("source_freshness_minutes", "valid_until")}
    bundle["bundle_hash"] = security.canonical_hash(hashable)
    return bundle
