-- Fact table: per-variant activation rate for each experiment.
-- This is the model MetricTrust's evidence broker reads freshness/test
-- state from before authorizing a rollout change.
select
    experiment_id,
    variant,
    count(*) as users,
    sum(activated_within_7d) as activated_users,
    round(sum(activated_within_7d) * 1.0 / count(*), 4) as activation_rate,
    max(event_ts) as last_event_ts
from {{ ref('stg_experiment_events') }}
group by 1, 2
