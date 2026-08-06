-- Staging: light typing/cleanup of raw assignment+activation events
select
    user_id,
    experiment_id,
    variant,
    cast(activated_within_7d as integer) as activated_within_7d,
    cast(event_ts as timestamp) as event_ts
from {{ ref('raw_experiment_events') }}
