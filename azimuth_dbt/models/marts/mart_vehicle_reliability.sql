-- One row per vehicle per lens: the current reliability record plus the
-- milestones the Maturation Race and the Scenario Simulator anchor on.
--
-- flights_to_lb_80 / flights_to_lb_90: the flight number at which the
-- lower bound of the 95% interval first reached 80% / 90%. This is the
-- answer to "how fast do vehicles earn reliability" in terms of evidence
-- rather than a point estimate. Null means the vehicle has not got there.
--
-- is_active: flew in the 24 months before the latest launch in the data.

with maturation as (

    select * from {{ ref('mart_maturation') }}

),

as_of as (

    select max(launched_at) as data_as_of
    from maturation

),

ranked as (

    select
        *,
        row_number() over (
            partition by lens, unit_key
            order by flight_number desc
        ) as recency_rank
    from maturation

),

latest as (

    select *
    from ranked
    where recency_rank = 1

),

milestones as (

    select
        lens,
        unit_key,
        min(launched_at)                                                as first_flight_at,
        max(launched_at)                                                as latest_flight_at,
        min(case when outcome = 'success' then flight_number end)      as first_success_flight,
        min(case when reliability_lower_95 >= 0.80 then flight_number end) as flights_to_lb_80,
        min(case when reliability_lower_95 >= 0.90 then flight_number end) as flights_to_lb_90
    from maturation
    group by lens, unit_key

)

select
    l.lens,
    l.unit_key,
    l.unit_name,
    l.flight_number                                   as flights,
    l.cum_successes                                   as successes,
    l.cum_failures                                    as failures,
    l.cum_partial_failures                            as partial_failures,
    l.cum_reliability                                 as reliability,
    l.reliability_lower_95,
    l.reliability_upper_95,
    m.first_flight_at,
    m.latest_flight_at,
    m.first_success_flight,
    m.flights_to_lb_80,
    m.flights_to_lb_90,
    m.latest_flight_at >= a.data_as_of - interval 730 days   as is_active,
    a.data_as_of

from latest l
join milestones m
    on l.lens = m.lens
    and l.unit_key = m.unit_key
cross join as_of a
