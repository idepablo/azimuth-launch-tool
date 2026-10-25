-- Cadence attempts must add up to the orbital launches in the fact table,
-- and every attempt must land in exactly one outcome bucket.
with cadence as (
    select
        sum(attempts) as attempts,
        sum(successes + failures + partial_failures) as outcomes
    from {{ ref('mart_cadence_yearly') }}
),
orbital as (
    select count(*) as n
    from {{ ref('fct_launches') }}
    where scope_class = 'orbital' and is_outcome_known
)
select *
from cadence
cross join orbital
where cadence.attempts <> orbital.n
   or cadence.outcomes <> orbital.n
