# Roadmap

This implementation is a scoped, solo-buildable vertical slice. The table below
is the honest production upgrade path for each simplification — what it would
take to move from "works and is tested" to "an enterprise would actually run
this in production."

## Identity

**Now:** static per-agent API keys, checked against `config/agents.yaml`.
**Next:** OIDC-issued short-lived tokens per agent, validated the same way a
human user's session token would be.
**Production:** SPIFFE/SPIRE workload identity — agents, the control plane,
and the executor each get an attested cryptographic identity with no shared
static secret anywhere. `spiffe.io` documents the attestation model this
would build on.

## Durable workflows

**Now:** approval state lives in the same database as everything else
(`Approval` rows with a status column), so it survives an API restart but has
no retry/escalation/timeout machinery beyond the TTL check already
implemented.
**Production:** Temporal, for real escalation chains ("no response in 4
hours → escalate to a second approver"), retries around flaky downstream
calls, and long-running remediation/rollback workflows that need to survive
infrastructure failures, not just process restarts.

## Policy engine

**Now:** a custom YAML rule engine with the same forbid/permit,
principal-action-resource-context shape as Cedar, evaluated by plain Python
comparisons.
**Production:** Cedar itself, for formal policy analysis and schema
validation the custom engine doesn't attempt — catching contradictory or
unreachable policies before they ship, not just at evaluation time.

## MCP-layer enforcement

**Now:** not implemented — the control plane is a plain FastAPI service the
agent calls via HTTP.
**Production:** a high-assurance MCP gateway (the original design specified
AgenTrust's cMCP) intercepting tool calls at the protocol layer with signed
TRACE claims and, for the highest-assurance deployments, hardware-backed
(TEE) attestation binding the policy bundle and signing key to the runtime.
This is genuinely developer-preview technology as of the original design
research — worth planning for, not worth faking in a portfolio project.

## Metric semantics

**Now:** a flat YAML metric registry (`config/metrics_registry.yaml`) —
approval status, owner, and a definition hash per metric.
**Production:** the dbt Semantic Layer / MetricFlow, so metric definitions,
dimensions, and entity relationships are defined once and reused by every
consuming application, not just this control plane.

## Lineage

**Now:** a small hashed lineage record built directly from the dbt run
(job name, invocation id, upstream models and seed).
**Production:** OpenLineage events emitted by every job in the pipeline,
giving MetricTrust (and everything else) a vendor-neutral, cross-tool lineage
graph instead of a single hand-built record.

## Catalog / governance metadata

**Now:** not implemented — ownership and certification live only in
`config/agents.yaml` and `config/metrics_registry.yaml`.
**Production:** OpenMetadata or DataHub for ownership, glossary terms,
certification status, and column-level lineage, queried by the evidence
broker instead of flat config files.

## Deployment

**Now:** `uvicorn` + SQLite/PostgreSQL, runnable with `pip install -r
requirements.txt`.
**Production:** containerized, Kubernetes + Helm, with the executor split
into a genuinely separate service/pod holding its own credentials (see
`docs/ARCHITECTURE.md`), managed Postgres/Redis, and object storage with
retention locks for the evidence/receipt archive.

## Observability

**Now:** structured Prometheus counters (`app/metrics.py`) exposed at
`/metrics`, using attribute names that match the `metrictrust.*` convention
this design settled on.
**Production:** full OpenTelemetry traces across the decision path (evidence
resolution → policy evaluation → approval → permit issuance → executor
verification → outcome), exported to a real collector/Grafana stack.

## Additional action types

**Now:** one action type (`update_experiment_rollout`) end to end.
**Production:** the same evidence-bundle / policy-rule / permit pattern
applied to campaign changes, pricing/promotion parameters, audience
activation, and fraud-threshold changes — the architecture doesn't change,
only the evidence sources and policy rules per action type do.
