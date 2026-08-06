-- Custom singular test standing in for "assignment integrity": fails if
-- either arm of the experiment has fewer than 5 users (a heavily
-- imbalanced or broken randomizer would trip this in a real pipeline).
select experiment_id, variant, count(*) as n_dummy
from {{ ref('stg_experiment_events') }}
group by 1, 2
having count(*) < 5
