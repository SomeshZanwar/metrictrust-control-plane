"""Minimal OpenTelemetry-style operational metrics via prometheus_client.

Attribute names deliberately mirror the metrictrust.* attribute set in the
original design doc so a real OTel exporter can be dropped in later
without renaming anything downstream (Grafana dashboards, alerts, etc.).
"""
from prometheus_client import Counter, Histogram

decisions_total = Counter(
    "metrictrust_decisions_total", "Policy decisions by outcome", ["decision"]
)
permits_issued_total = Counter(
    "metrictrust_permits_issued_total", "Execution permits issued"
)
executions_total = Counter(
    "metrictrust_executions_total", "Executor outcomes", ["result"]
)
decision_latency_seconds = Histogram(
    "metrictrust_decision_latency_seconds", "Time to evaluate one action end-to-end"
)
