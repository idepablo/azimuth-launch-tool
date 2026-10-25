-- Every orbital flight in mart_maturation lands in exactly one band of the
-- debut curve: the pooled era ('all') and the sum of the eras both match
-- the maturation row count per lens.
with maturation as (
    select lens, count(*) as flights
    from {{ ref('mart_maturation') }}
    group by lens
),
curve as (
    select
        lens,
        sum(case when era = 'all' then attempts else 0 end)  as pooled,
        sum(case when era <> 'all' then attempts else 0 end) as by_era
    from {{ ref('mart_debut_curve') }}
    group by lens
)
select m.lens, m.flights, c.pooled, c.by_era
from maturation m
left join curve c on m.lens = c.lens
where c.pooled is null or c.pooled <> m.flights or c.by_era <> m.flights
