-- Launch cadence: one row per year and provider, Earth orbital scope only.
--
-- Outcomes keep the three-way split from docs/scope.md: success
-- (status 3 or 9), failure (4) and partial failure (7) are counted
-- separately, never collapsed.
--
-- The latest year is incomplete by definition. is_partial_year flags it
-- so charts can mark it instead of showing it as a drop in cadence.

with launches as (

    select * from {{ ref('fct_launches') }}

),

providers as (

    select * from {{ ref('dim_provider') }}

),

as_of as (

    select max(launched_at) as data_as_of
    from launches

),

orbital as (

    select *
    from launches
    where scope_class = 'orbital'
      and is_outcome_known

)

select
    year(o.launched_at)                                         as launch_year,
    o.provider_key,
    p.provider_name,
    p.country,
    p.sector,
    count(*)                                                    as attempts,
    sum(case when o.status_id in ('3', '9') then 1 else 0 end)  as successes,
    sum(case when o.status_id = '4' then 1 else 0 end)          as failures,
    sum(case when o.status_id = '7' then 1 else 0 end)          as partial_failures,
    year(o.launched_at) = year(a.data_as_of)                    as is_partial_year,
    a.data_as_of

from orbital o
join providers p
    on o.provider_key = p.provider_key
cross join as_of a
group by
    year(o.launched_at),
    o.provider_key,
    p.provider_name,
    p.country,
    p.sector,
    a.data_as_of
