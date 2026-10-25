-- Both lenses describe the same set of orbital launches: same row count,
-- and that count matches the orbital launches in the fact table.
with lens_counts as (
    select lens, count(*) as n
    from {{ ref('mart_maturation') }}
    group by lens
),
orbital as (
    select count(*) as n
    from {{ ref('fct_launches') }}
    where scope_class = 'orbital' and is_outcome_known
)
select l.lens, l.n, o.n as orbital_launches
from lens_counts l
cross join orbital o
where l.n <> o.n
