> **Note:** this is the original full enterprise-architecture concept this project started from. `README.md` and `ROADMAP.md` in the repository root explain exactly which pieces of this were implemented as-is, which were scoped down to something solo-buildable, and what the upgrade path back to this design looks like. Kept here in full for reference.

---

# Optimized industry-ready concept

## **MetricTrust Control Plane**

### Evidence-bound execution for enterprise data and analytics agents

The original idea—blocking an agent when data is stale or a dbt test fails—is no longer differentiated enough by itself. Data-observability vendors now expose trust and quality signals directly to AI agents, while analytics platforms are moving from insight generation toward autonomous action. The market gap is no longer simply **“Can the agent see whether the data is trustworthy?”** It is:

> **Can the enterprise guarantee that an operational action was executed only under the exact data, metric, policy, identity and approval state that authorized it?**

Actian already exposes data-observability signals through MCP so agents can verify data before acting. Tableau, Google Cloud and other data platforms are also positioning enterprise data as a foundation for agent-driven action. Meanwhile, Gartner recommends proportional controls based on agent autonomy, including approval workflows, circuit breakers, rollback mechanisms and continuous monitoring for autonomous agents. ([Actian][1])

That changes the project from a **data-quality demo** into a genuine **enterprise agent-control product**.

---

# 1. Product definition

MetricTrust is a pre-execution control plane placed between autonomous data agents and enterprise systems of action.

It evaluates whether an agent’s proposed action is supported by current, approved and independently verifiable business evidence. When the conditions are satisfied, MetricTrust issues a signed, short-lived execution permit. The downstream system executes the action only after verifying that permit.

```text
Analytics agent
      |
      | proposes an operational action
      v
MetricTrust Control Plane
      |
      |-- verifies agent identity
      |-- retrieves evidence state
      |-- verifies metric semantics
      |-- verifies data quality and freshness
      |-- verifies lineage and source certification
      |-- verifies delegated authority
      |-- verifies human approval when required
      |-- evaluates deterministic policy
      |
      +---- DENY
      |
      +---- REQUIRE APPROVAL
      |
      +---- ISSUE SIGNED EXECUTION PERMIT
                         |
                         v
                 Protected Executor
                         |
                         v
                Enterprise application
```

## Core promise

> **No high-impact agent action executes without a valid permit bound to the exact evidence that justified it.**

This is stronger than:

* giving the agent access to quality metadata;
* asking the model to inspect a dbt report;
* maintaining an audit log;
* requiring a generic human approval;
* checking whether the agent is allowed to call a tool;
* detecting problems after the action has happened.

---

# 2. What MetricTrust actually governs

MetricTrust should govern **business-changing actions**, not every analytical query.

Examples include:

* changing an experiment rollout;
* pausing or modifying a marketing campaign;
* publishing an executive KPI;
* changing a customer segment;
* pushing an audience into an activation platform;
* modifying pricing or promotion parameters;
* triggering a retention campaign;
* updating a forecast used by operational planning;
* changing a fraud or risk threshold;
* creating or modifying a production feature flag.

Read-only exploration remains lightweight. Governance becomes stricter as the agent’s autonomy and blast radius increase.

This proportional approach reflects the current enterprise direction: observe-only and advisory agents need lighter controls, while agents that write to systems require approvals, enforced guardrails, incident procedures, circuit breakers and rollback capability. ([Gartner][2])

---

# 3. Recommended first industry use case

## **Governed experiment-rollout agent**

The first implementation should focus on a product analytics agent controlling an experiment or feature rollout.

This is better than starting with a generic “pause campaign” demo because it is:

* directly related to product analytics;
* easy to simulate with realistic event data;
* reversible;
* measurable;
* understandable to product managers;
* portable across feature-flag vendors;
* suitable for graduated autonomy;
* safe to demonstrate without financial or medical regulatory claims.

OpenFeature provides a vendor-neutral specification and API for feature-flagging, allowing the project to support an open-source flag provider initially and commercial platforms later without rewriting its business logic. ([OpenFeature][3])

## Example scenario

A product analytics agent monitors a new onboarding experience.

It detects:

```text
Activation rate:
Control:   61.2%
Treatment: 67.8%

Recommended action:
Increase treatment rollout from 20% to 50%.
```

The agent requests:

```json
{
  "action": "update_experiment_rollout",
  "experiment_id": "onboarding-v4",
  "current_percentage": 20,
  "requested_percentage": 50,
  "metric": "seven_day_activation_rate",
  "reason": "Treatment outperforms control"
}
```

MetricTrust does not evaluate whether the model’s prose sounds convincing. It verifies the evidence.

```text
Metric definition approved?                  YES
Metric version current?                      YES
Source data fresh?                           YES
Critical dbt tests passing?                  YES
Experiment assignment integrity passing?     YES
Minimum sample size reached?                  YES
Guardrail metrics within limits?              YES
Lineage complete?                            YES
Dataset snapshot unchanged?                  YES
Agent authorized for 50% rollout?             NO
Human approval attached?                      NO
```

Result:

```text
REQUIRE APPROVAL

Reason:
The agent has autonomous authority up to 25%.
Rollouts above 25% require Product Owner approval.
```

After approval, MetricTrust issues a permit bound to:

* experiment `onboarding-v4`;
* rollout change `20% → 50%`;
* the exact metric definition;
* the exact dataset snapshot;
* the exact quality-test results;
* the current policy version;
* the approving person;
* a short expiration window.

The permit cannot be reused to roll the experiment to 100%, change another feature or execute after the evidence becomes stale.

---

# 4. The real product innovation

## Evidence-bound execution permits

The most important component is not the dashboard, data-quality score or agent.

It is the **execution permit**.

A permit should contain—or cryptographically commit to—the following:

```json
{
  "permit_id": "permit_01J...",
  "subject": "spiffe://company.ai/agents/product-analytics-01",
  "audience": "experiment-control-executor",
  "action": "update_experiment_rollout",
  "resource": "experiment/onboarding-v4",
  "parameters_hash": "sha256:...",
  "evidence_bundle_hash": "sha256:...",
  "metric_definition_hash": "sha256:...",
  "dataset_snapshot_hash": "sha256:...",
  "lineage_closure_hash": "sha256:...",
  "policy_bundle_hash": "sha256:...",
  "approval_id": "approval_01J...",
  "issued_at": "2026-08-03T18:00:00Z",
  "expires_at": "2026-08-03T18:10:00Z",
  "nonce": "random-single-use-value",
  "risk_tier": "high",
  "signature": "..."
}
```

## Why this matters

Without evidence binding, the following failure is possible:

1. The agent analyzes dataset snapshot A.
2. A manager approves the action.
3. The pipeline refreshes and creates snapshot B.
4. The quality state changes.
5. The agent executes using the old approval.
6. The audit log still says that approval existed.

MetricTrust prevents this because the approval and permit are bound to snapshot A. Once the data changes, the permit becomes invalid.

This closes the gap between:

```text
“The action was approved at some point”
```

and:

```text
“This exact action was approved under this exact evidence state.”
```

---

# 5. Industry architecture

## Control-plane architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                    Agent Applications                       │
│  Product Agent | Growth Agent | RevOps Agent | Risk Agent   │
│  Microsoft Agent Framework / LangGraph / custom runtime     │
└──────────────────────────────┬──────────────────────────────┘
                               │ MCP tool request
                               v
┌─────────────────────────────────────────────────────────────┐
│                Agent Governance Boundary                    │
│                                                             │
│  Microsoft AGT middleware/sidecar                           │
│  • agent identity and delegation                            │
│  • tool interception                                        │
│  • action classification                                    │
│  • rate limits and authority boundaries                     │
│  • audit and operational controls                           │
└──────────────────────────────┬──────────────────────────────┘
                               │ evidence-aware request
                               v
┌─────────────────────────────────────────────────────────────┐
│                  MetricTrust Control Plane                  │
│                                                             │
│  1. Evidence Broker                                         │
│  2. Metric & Semantic Resolver                              │
│  3. Lineage Resolver                                        │
│  4. Risk Classifier                                         │
│  5. Cedar Policy Decision Point                             │
│  6. Approval Workflow Manager                               │
│  7. Permit Issuer                                           │
│  8. Receipt Generator                                       │
└───────────────┬───────────────────────────────┬─────────────┘
                │                               │
                v                               v
┌──────────────────────────┐       ┌──────────────────────────┐
│ Enterprise Evidence      │       │ Human Control Systems    │
│                          │       │                          │
│ dbt artifacts            │       │ Microsoft Teams/Slack    │
│ dbt Semantic Layer       │       │ Entra ID / OIDC          │
│ OpenLineage              │       │ Approval portal          │
│ OpenMetadata/DataHub     │       │ Escalation workflows     │
│ Warehouse snapshots      │       └──────────────────────────┘
│ Data contracts           │
└──────────────────────────┘
                |
                v
┌─────────────────────────────────────────────────────────────┐
│                   Protected Executor                        │
│  Verifies signature, scope, freshness, audience and nonce   │
└──────────────────────────────┬──────────────────────────────┘
                               |
                               v
┌─────────────────────────────────────────────────────────────┐
│                    Systems of Action                        │
│  OpenFeature | Google Ads | CRM | CDP | Pricing | ERP       │
└─────────────────────────────────────────────────────────────┘
```

---

# 6. Recommended technology stack

The project should use modern enterprise components, but it should not become a collection of tools with no architectural purpose.

## A. Agent orchestration

### Primary recommendation

* **Microsoft Agent Framework or an AGT-supported agent adapter**
* Python for the initial implementation
* FastAPI for the application and control-plane APIs
* Pydantic for typed action and evidence schemas

The agent framework should remain replaceable. MetricTrust must govern the action independently of whether the agent uses Microsoft Agent Framework, LangGraph or another orchestrator.

---

## B. Runtime action governance

### Microsoft Agent Governance Toolkit

Use AGT for:

* tool interception;
* agent identity;
* delegated authority;
* policy enforcement integration;
* rate limits;
* approval requirements;
* governance telemetry;
* kill-switch and circuit-breaker integration;
* container or sidecar deployment.

AGT supports application-layer interception of MCP tool calls and can be deployed as middleware or a Kubernetes sidecar. Its current releases also include an external policy-backend interface, governance event sinks, OpenTelemetry bootstrap, Prometheus metrics and a dbt data-quality evidence adapter example. ([GitHub][4])

### Important engineering qualification

AGT is currently a public-preview project. It describes its releases as production-quality but warns that APIs may change before general availability. Therefore:

* pin the AGT version;
* isolate AGT behind an internal adapter;
* do not scatter AGT-specific objects throughout the codebase;
* add contract tests around the adapter;
* retain a fallback policy-enforcement interface.

([GitHub][5])

---

## C. High-assurance MCP gateway

### AgenTrust cMCP

Use cMCP as the **high-assurance deployment mode**, not as a mandatory dependency for the first release.

cMCP intercepts MCP calls, evaluates Cedar policies, supports allow/deny/redact outcomes and produces signed TRACE claims. Hardware-backed operation can bind the policy bundle and signing key to a TEE. It also supports software-only development mode, advisory rollout and enforcing mode. ([GitHub][6])

Recommended operating modes:

| Environment               | Enforcement                     |
| ------------------------- | ------------------------------- |
| Local development         | cMCP software mode              |
| Integration testing       | Advisory                        |
| Staging                   | Enforcing with software signing |
| Enterprise high-assurance | Enforcing with TEE attestation  |

cMCP is a developer-preview technology, so MetricTrust should expose a general `GovernanceGateway` interface with cMCP as one implementation. ([GitHub][6])

---

## D. Policy engine

### Cedar

Use Cedar as the primary authorization policy language.

Reasons:

* native alignment with cMCP;
* supported by AGT;
* clear principal–action–resource model;
* suitable for attribute-based controls;
* policies remain separate from application code;
* schemas and validators can catch incorrect policy structures;
* policies can be versioned, reviewed and tested independently.

Cedar is explicitly designed for fine-grained authorization and supports policy analysis and schema validation. ([GitHub][7])

Do not use both Cedar and OPA in the first version. A dual-policy architecture would add unnecessary conflict-resolution and operational complexity.

---

## E. Data transformation and quality

### dbt

Use dbt for:

* transformation logic;
* source freshness;
* schema tests;
* relationship tests;
* business-specific tests;
* model dependencies;
* run identifiers;
* artifact production;
* version-controlled analytics logic.

Evidence should be extracted from:

```text
manifest.json
run_results.json
sources.json
semantic_manifest.json
```

The evidence adapter should not reduce these artifacts to one arbitrary “trust score.” It should produce discrete, policy-readable claims such as:

```json
{
  "critical_tests_failed": 0,
  "source_freshness_minutes": 18,
  "dbt_invocation_id": "...",
  "model_unique_id": "model.product.fct_experiment_outcomes",
  "manifest_hash": "sha256:...",
  "run_results_hash": "sha256:..."
}
```

A binary or structured evidence model is more auditable than an unexplained composite score.

---

## F. Metric semantics

### dbt Semantic Layer / MetricFlow

Use the semantic layer to resolve:

* metric identifier;
* approved definition;
* numerator and denominator;
* dimensions;
* filters;
* entity relationships;
* ownership;
* effective version;
* semantic-manifest hash.

The dbt Semantic Layer centralizes metric definitions and handles joins so the same metric logic can be reused across consuming applications. ([dbt Developer Hub][8])

MetricTrust adds the missing execution control:

> The semantic layer defines the metric. MetricTrust determines whether the metric’s current evidence state is sufficient to authorize an action.

---

## G. Lineage

### OpenLineage

Use OpenLineage as the vendor-neutral lineage event format.

Store:

* job namespace and name;
* run ID;
* run state;
* input datasets;
* output datasets;
* producer identifier;
* event timestamp;
* custom evidence facets.

OpenLineage defines interoperable dataset, job and run entities, and its API supports lifecycle events including start, running, complete, abort and fail. ([OpenLineage][9])

Create a custom MetricTrust facet:

```json
{
  "_producer": "metrictrust-control-plane",
  "_schemaURL": "https://metrictrust.dev/schemas/evidence-facet-v1.json",
  "evidenceBundleId": "ev_01J...",
  "metricDefinitionHash": "sha256:...",
  "qualityState": "PASS",
  "policyEligible": true
}
```

---

## H. Catalog and governance metadata

### Initial implementation: OpenMetadata

Use OpenMetadata for:

* ownership;
* domains;
* glossary terms;
* classifications;
* certification status;
* data-quality results;
* table and column lineage;
* approval state of business terms;
* asset tier and criticality.

OpenMetadata supports governed glossary terms with owners, reviewers, approval status and version history, as well as column-level lineage and data-quality context. ([OpenMetadata Documentation][10])

### Enterprise adapter layer

Define a catalog adapter so that later deployments can use:

* DataHub;
* Collibra;
* Alation;
* Microsoft Purview;
* OpenMetadata.

Do not build a custom catalog.

---

## I. Feature-flag and experiment execution

### OpenFeature

Use OpenFeature as the abstraction for feature rollout.

Initial local provider:

* `flagd`, Flagsmith or another OpenFeature-compatible provider.

Future integrations:

* LaunchDarkly;
* Split;
* ConfigCat;
* cloud-native feature-management systems.

The protected executor receives the MetricTrust permit, verifies it, and then calls the selected OpenFeature provider.

The agent should never receive direct credentials for the feature-flag control plane.

---

## J. Durable approvals and remediation workflows

### Temporal

Use Temporal for:

* human approval workflows;
* approval expiry;
* escalation;
* retries;
* timeout handling;
* remediation workflows;
* rollback orchestration;
* evidence-refresh workflows.

An approval may remain pending for hours or days. It should survive service restarts and network failures. Temporal is designed for durable workflow execution that resumes after infrastructure failures. ([Temporal Docs][11])

Example workflow:

```text
Policy returns REQUIRE_APPROVAL
        |
        v
Create Temporal workflow
        |
        +-- notify Product Owner
        +-- wait for approval
        +-- expire after 4 hours
        +-- refresh evidence
        +-- re-evaluate policy
        +-- issue permit
        +-- execute action
        +-- verify outcome
        +-- rollback on failed guardrail
```

Approval alone must not immediately authorize execution. After approval, the evidence must be refreshed and the policy evaluated again.

---

## K. Workload identity

### Local and MVP

* OIDC service identities;
* JWT validation;
* asymmetric signing keys;
* separate identity for each agent and executor.

### Production

* SPIFFE/SPIRE for workload identity;
* Entra Workload Identity where the deployment is Azure-based;
* mTLS between control-plane components.

SPIRE attests workloads and issues cryptographic identities based on registered workload properties, making it appropriate for identifying agents, gateways and executors without shared static API keys. ([SPIFFE][12])

The identity model should distinguish:

```text
Human user
Agent workload
Governance gateway
Evidence collector
Permit issuer
Protected executor
Target integration
```

---

## L. MCP authorization

Use HTTP-based MCP with OAuth-aligned authorization, audience validation and separate tokens for separate MCP resources.

The MCP authorization specification requires protected-resource metadata when HTTP authorization is supported and explicitly emphasizes audience validation and avoiding token passthrough. ([Model Context Protocol][13])

The agent must not be able to reuse:

```text
a warehouse token
```

to call:

```text
the experiment-control server
```

Each protected MCP server should have an explicit audience and narrowly scoped access.

---

## M. Operational state and storage

### PostgreSQL

Use PostgreSQL for:

* policy metadata;
* agent registry;
* action classifications;
* evidence-bundle indexes;
* approval records;
* permit state;
* replay-protection records;
* integration configurations.

### Redis

Use Redis for:

* short-lived evidence-state cache;
* nonce consumption;
* rate limiting;
* circuit-breaker state;
* policy decision cache.

### Object storage

Use S3, Azure Blob or GCS for:

* immutable evidence bundles;
* TRACE claims;
* policy bundles;
* dbt artifacts;
* exported audit packages.

Use versioning and retention-lock/WORM options for production evidence storage.

Do not store raw customer data in the receipt. Store:

* hashes;
* dataset identifiers;
* snapshot IDs;
* encrypted references;
* aggregate quality results.

---

## N. Observability

### OpenTelemetry

Instrument the complete path:

```text
Agent request
→ evidence resolution
→ policy evaluation
→ approval
→ permit issuance
→ executor verification
→ external action
→ outcome validation
```

OpenTelemetry maintains GenAI-related semantic conventions for models, agents and data sources, which can be extended with MetricTrust-specific governance attributes. ([OpenTelemetry][14])

Recommended attributes:

```text
metrictrust.decision_id
metrictrust.action_type
metrictrust.risk_tier
metrictrust.policy_bundle_hash
metrictrust.evidence_bundle_id
metrictrust.metric_definition_hash
metrictrust.decision
metrictrust.denial_reason
metrictrust.approval_required
metrictrust.permit_id
metrictrust.executor_result
```

Use:

* OpenTelemetry Collector;
* Prometheus;
* Grafana;
* Loki or a structured log backend;
* optional Tempo or Jaeger for traces.

The dashboard should measure governance operation, not merely display colorful agent cards.

---

# 7. Product risk model

Classify actions into four levels.

| Level                              | Agent behavior                | MetricTrust control                                         |
| ---------------------------------- | ----------------------------- | ----------------------------------------------------------- |
| **L1 — Observe**                   | Read metadata and metrics     | Identity, access control, logging                           |
| **L2 — Advise**                    | Generate recommendation       | Evidence disclosure, confidence and lineage                 |
| **L3 — Act with approval**         | Propose a write action        | Evidence validation plus scoped human approval              |
| **L4 — Bounded autonomous action** | Execute inside defined limits | Permit, continuous monitoring, circuit breaker and rollback |

## Example authority limits

```yaml
agent: product-analytics-agent

authority:
  update_experiment_rollout:
    autonomous_max_percentage: 25
    approval_max_percentage: 50
    prohibited_above_percentage: 50

  pause_experiment:
    autonomous: false
    approval_required: true

  publish_metric_annotation:
    autonomous: true
```

This avoids treating every agent and every action identically.

---

# 8. Evidence model

Each action should receive a structured **Decision Evidence Bundle**.

## Identity evidence

```text
Agent ID
Agent owner
Deployment environment
Workload identity
Delegated authority
Agent version
Container or artifact digest
```

## Data evidence

```text
Dataset IDs
Warehouse snapshot or partition IDs
Freshness timestamps
dbt invocation ID
Critical test results
Schema version
Row-count and completeness assertions
```

## Semantic evidence

```text
Metric URN
Metric version
Metric-definition hash
Business glossary term
Glossary approval state
Metric owner
Permitted dimensions and filters
```

## Lineage evidence

```text
OpenLineage run IDs
Upstream datasets
Transformation jobs
Lineage-closure hash
Failed upstream run state
Unregistered-source indicators
```

## Action evidence

```text
Tool name
Resource
Parameters hash
Expected blast radius
Reversibility
Rollback operation
Requested autonomy level
```

## Approval evidence

```text
Approver identity
Role
Approval scope
Approved parameters
Evidence-bundle hash
Approval timestamp
Expiry
Separation-of-duties result
```

## Governance evidence

```text
Policy bundle hash
Policy decision
Matched rules
Conflict-resolution result
Permit ID
Receipt ID
Runtime or TEE evidence
```

---

# 9. Policy examples

## Stale-source policy

```cedar
forbid (
    principal,
    action == Action::"UpdateExperimentRollout",
    resource
)
when {
    context.evidence.critical_source_age_minutes >
    context.policy.max_source_age_minutes
};
```

## Unapproved metric policy

```cedar
forbid (
    principal,
    action,
    resource
)
when {
    context.evidence.metric_approval_status != "APPROVED"
};
```

## Failed experiment-integrity test

```cedar
forbid (
    principal,
    action == Action::"UpdateExperimentRollout",
    resource
)
when {
    context.evidence.assignment_integrity_test != "PASS"
};
```

## Bounded autonomy

```cedar
permit (
    principal in AgentGroup::"ProductAnalyticsAgents",
    action == Action::"UpdateExperimentRollout",
    resource
)
when {
    context.requested_rollout_percentage <= 25 &&
    context.evidence.quality_state == "PASS" &&
    context.evidence.guardrail_state == "PASS"
};
```

## Approval binding

```cedar
forbid (
    principal,
    action,
    resource
)
when {
    context.approval.evidence_bundle_hash !=
    context.evidence.bundle_hash
};
```

## Expired evidence

```cedar
forbid (
    principal,
    action,
    resource
)
when {
    context.current_time_epoch >
    context.evidence.valid_until_epoch
};
```

---

# 10. Protected execution

A governance system is incomplete if the agent can bypass it.

Therefore, the actual feature-flag or campaign credential must be available only to the protected executor.

```text
Agent credentials:
- query analytics
- request actions
- cannot mutate feature flags

Protected executor credentials:
- can mutate feature flags
- accepts only signed MetricTrust permits
- cannot generate permits
```

The executor verifies:

1. Signature.
2. Issuer.
3. Audience.
4. Action name.
5. Resource.
6. Parameter hash.
7. Expiration.
8. Nonce.
9. Single-use status.
10. Environment.
11. Policy version, when pinned.
12. Evidence bundle, when required.

This separation creates a real security boundary.

Without it, the gateway is merely advisory.

---

# 11. Circuit breakers and rollback

For autonomous operation, the project needs post-execution controls as well.

Example:

```text
Agent increases rollout from 20% to 25%
            |
            v
MetricTrust starts monitoring guardrails
            |
            +-- error rate increases by 2.5%
            +-- support contacts rise
            +-- payment failures rise
            |
            v
Circuit breaker activates
            |
            v
Rollout automatically returns to 20%
```

Every action definition should specify:

```yaml
action: update_experiment_rollout

preconditions:
  - activation_metric_valid
  - guardrail_metrics_valid
  - assignment_integrity_valid

postconditions:
  - flag_state_matches_requested_value

rollback:
  action: restore_previous_rollout
  maximum_execution_seconds: 30

circuit_breakers:
  - metric: application_error_rate
    threshold_change: 0.02
    window_minutes: 15
```

---

# 12. Enterprise user experience

Do not make Streamlit the primary interface.

Use:

* **Next.js/React** for the governance console;
* **FastAPI** for the backend;
* server-sent events or WebSockets for live decision updates;
* role-based views.

## Required screens

### Action queue

Shows:

* proposed action;
* agent;
* affected resource;
* risk tier;
* expected blast radius;
* evidence status;
* approval requirement.

### Decision evidence

Shows:

* metric definition;
* data freshness;
* failed tests;
* lineage;
* action parameters;
* matched policies;
* denial reasons.

### Approval interface

Approvers must see:

* exactly what will change;
* why the agent proposed it;
* affected users;
* rollback plan;
* evidence age;
* guardrail status;
* approval expiration.

### Agent registry

Shows:

* agent owner;
* identity;
* deployment;
* authority;
* allowed tools;
* current risk level;
* last activity;
* kill-switch status.

### Audit and verification

Allows a user to:

* download the evidence bundle;
* verify the permit;
* verify the TRACE claim;
* reconstruct the decision;
* compare the policy bundle;
* validate the action outcome.

---

# 13. Deployment model

## Local development

```text
Docker Compose
PostgreSQL
Redis
DuckDB
dbt Core
OpenMetadata
OpenLineage/Marquez
flagd
AGT
cMCP software mode
FastAPI
Next.js
OTel Collector
Prometheus
Grafana
```

## Enterprise deployment

```text
Kubernetes
Helm
Terraform
Managed PostgreSQL
Managed Redis
Object storage with retention controls
SPIRE or cloud workload identity
AGT sidecars
MetricTrust services
cMCP high-assurance gateway
OpenTelemetry Collector
Prometheus/Grafana
Cloud KMS or Vault
Enterprise IdP
```

## Cloud neutrality

Keep adapters for:

* Snowflake, BigQuery and Databricks;
* AWS, Azure and GCP object storage;
* Entra ID, Okta and generic OIDC;
* DataHub, OpenMetadata and enterprise catalogs;
* LaunchDarkly and other OpenFeature providers;
* Teams and Slack approvals.

The first implementation only needs one working option per category.

---

# 14. Non-functional product requirements

These are targets, not current performance claims.

## Reliability

* Control plane availability target: **99.9%**
* Policy decisions fail closed for high-risk actions.
* Evidence-source outages result in deny or approval escalation.
* Approval workflows survive process restarts.
* All external actions use idempotency keys.
* Every action has a known final state.

## Performance

* Precompute evidence state instead of querying every source during the hot path.
* Target p95 policy decision latency: **under 100 ms** with cached evidence.
* Target p95 full permit issuance: **under 300 ms**, excluding human approval.
* Evidence refresh runs asynchronously.
* High-cost lineage closure is calculated before the action request.

## Security

* No shared credentials between agents.
* No target-system credentials inside agent containers.
* Short-lived permits.
* Single-use nonces.
* mTLS between internal services.
* KMS-backed signing.
* Secret rotation.
* Signed container images.
* SBOM generation.
* Dependency and image scanning.
* Default-deny for unknown actions.
* Separate production and non-production trust domains.

## Privacy

* Receipts store hashes and references, not raw records.
* Sensitive action parameters can be encrypted.
* Telemetry must redact prompts and payloads by default.
* Data-retention rules must be configurable by evidence type.

---

# 15. Integration roadmap

## Release 1 — Industry-grade vertical slice

Build one complete workflow:

```text
Product analytics agent
→ dbt evidence
→ semantic metric
→ OpenLineage
→ Cedar policy
→ approval workflow
→ execution permit
→ OpenFeature rollout
→ receipt
→ rollback
```

Technologies:

* Python;
* FastAPI;
* PostgreSQL;
* Redis;
* dbt Core;
* DuckDB;
* OpenLineage;
* OpenMetadata;
* AGT;
* Cedar;
* OpenFeature/flagd;
* Temporal;
* Next.js;
* OpenTelemetry;
* Prometheus/Grafana.

## Release 2 — Enterprise connectors

Add:

* Snowflake or BigQuery;
* dbt Cloud;
* LaunchDarkly;
* Microsoft Teams approval;
* Entra ID;
* cloud object storage;
* cloud KMS;
* Kubernetes and Helm.

## Release 3 — Assurance layer

Add:

* cMCP enforcement;
* signed TRACE claims;
* hardware-backed deployment option;
* WORM evidence archive;
* independent verifier CLI;
* cross-environment policy promotion.

## Release 4 — Multi-use-case platform

Add adapters for:

* marketing campaigns;
* customer-segment activation;
* pricing;
* sales operations;
* fraud thresholds;
* executive metric publication.

---

# 16. What should not be built

To keep this credible and industry-focused, avoid these traps:

### Do not build a new data catalog

Integrate with OpenMetadata or DataHub.

### Do not build a new feature-flag product

Use OpenFeature.

### Do not use blockchain

Signed permits, append-only storage and TRACE evidence are sufficient.

### Do not put an LLM in the enforcement decision

An LLM may summarize the evidence, but deterministic policy makes the decision.

### Do not query every source during every tool call

Maintain signed or hashed evidence snapshots with explicit validity windows.

### Do not start with hardware attestation

Design for cMCP and TEE-backed execution, but first make the software control boundary correct.

### Do not create a universal “data trust score”

Expose explicit predicates:

```text
freshness_passed
critical_tests_passed
metric_approved
lineage_complete
approval_valid
```

A single score is difficult to audit and can hide critical failures.

### Do not make the dashboard the project

The product is the enforceable permit boundary. The dashboard is only its operating interface.

---

# 17. Industry positioning

## Category

**Evidence-aware runtime governance for autonomous data agents**

## Buyer

Primary:

* Head of Data Platform;
* Head of AI Platform;
* Chief Data Officer;
* AI Governance Lead;
* Product Analytics or Experimentation Platform Lead.

Secondary:

* CISO;
* Internal Audit;
* Model Risk;
* Data Governance;
* Product Operations.

## Business problem

> Enterprises want analytics agents to act, but existing controls separately manage data quality, semantic definitions, agent permissions and human approvals. They do not reliably bind those elements together at execution time.

## Product value

MetricTrust enables organizations to:

* increase agent autonomy without granting unrestricted write access;
* prevent actions based on stale or invalid business evidence;
* reduce generic approval fatigue;
* enforce bounded autonomy;
* produce reconstructible decision evidence;
* demonstrate who or what authorized an action;
* implement automatic rollback and circuit breakers;
* remain independent of a single data, agent or feature-flag vendor.

## Differentiation

| Product category   | Existing capability         | MetricTrust addition                            |
| ------------------ | --------------------------- | ----------------------------------------------- |
| Data observability | Detect bad or stale data    | Prevent operational actions based on it         |
| Semantic layer     | Define consistent metrics   | Bind action authority to the metric version     |
| Data catalog       | Track ownership and lineage | Use certification and lineage in runtime policy |
| Agent governance   | Control tool access         | Require business evidence for tool execution    |
| Human approval     | Approve proposed action     | Bind approval to exact evidence and parameters  |
| Audit logging      | Record what happened        | Produce verifiable pre-execution authorization  |
| Feature flags      | Execute rollout changes     | Require signed evidence-bound permits           |

---

# 18. Final optimized framing

## Product name

**MetricTrust Control Plane**

## One-line description

> MetricTrust is a pre-execution control plane that allows enterprise data agents to perform business-changing actions only when the exact data, metric, lineage, policy and approval evidence supporting the action is valid and verifiable.

## Core demonstration

> A product analytics agent correctly identifies an apparent experiment improvement and requests a larger rollout. MetricTrust blocks the action—not because the model violated a prompt, but because an upstream assignment-integrity test failed. After the data is repaired and a scoped approval is issued, MetricTrust creates a short-lived permit bound to the corrected dataset and executes the rollout through a protected OpenFeature executor.

## Strong product message

> **Trusted data should not merely inform an agent. It should determine whether the agent has authority to act.**

## Strong technical message

> **Identity says which agent requested the action. Policy says what it may do. Evidence says whether it may do it now. The execution permit binds all three.**

## Repository subtitle

> Evidence-bound execution control for autonomous product analytics and enterprise data agents.

This version is substantially more industry-ready than the original concept because it includes an enforceable security boundary, durable approval workflows, protected credentials, workload identity, replay-resistant permits, lifecycle observability, circuit breakers, rollback and real enterprise integrations—not only a model, policy file and demonstration dashboard.

[1]: https://www.actian.com/company/press-releases/actian-introduces-data-observability-agents-for-the-agentic-ai-era/?utm_source=chatgpt.com "Data Observability Agents for the Agentic AI Era Explained"
[2]: https://www.gartner.com/en/newsroom/press-releases/2026-05-26-gartner-says-applying-uniform-governance-across-ai-agents-will-lead-to-enterprise-ai-agent-failure?utm_source=chatgpt.com "Gartner Says Applying Uniform Governance Across AI Agents Will Lead to Enterprise AI Agent Failure"
[3]: https://openfeature.dev/?utm_source=chatgpt.com "OpenFeature"
[4]: https://github.com/microsoft/agent-governance-toolkit/blob/main/docs/FAQ.md?utm_source=chatgpt.com "agent-governance-toolkit/docs/FAQ.md at main · microsoft/agent-governance-toolkit · GitHub"
[5]: https://github.com/microsoft/agent-governance-toolkit/releases?utm_source=chatgpt.com "Releases · microsoft/agent-governance-toolkit · GitHub"
[6]: https://github.com/agentrust-io/cmcp "GitHub - agentrust-io/cmcp: cMCP: Confidential MCP Gateway. Hardware-attested policy enforcement for MCP tool calls. · GitHub"
[7]: https://github.com/cedar-policy?utm_source=chatgpt.com "cedar-policy · GitHub"
[8]: https://docs.getdbt.com/docs/use-dbt-semantic-layer/dbt-sl "dbt Semantic Layer | dbt Developer Hub"
[9]: https://openlineage.io/apidocs/openapi/?utm_source=chatgpt.com "OpenLineage API Docs"
[10]: https://docs.open-metadata.org/v1.12.x/how-to-guides/data-governance/glossary/setup?utm_source=chatgpt.com "How to Setup a Glossary | Official Documentation - OpenMetadata Documentation"
[11]: https://docs.temporal.io/?utm_source=chatgpt.com "Temporal Docs | Temporal Platform Documentation"
[12]: https://spiffe.io/docs/latest/spire-about/spire-concepts/?utm_source=chatgpt.com "SPIRE Concepts | SPIFFE"
[13]: https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization?utm_source=chatgpt.com "Authorization - Model Context Protocol"
[14]: https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/?utm_source=chatgpt.com "Gen AI | OpenTelemetry"
