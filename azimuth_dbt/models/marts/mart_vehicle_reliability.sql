-- One row per vehicle per lens: the current reliability record plus the
-- milestones the Maturation Race and the Scenario Simulator anchor on.
--
-- flights_to_lb_80 / flights_to_lb_90: the flight number at which the
-- lower bound of the 95% interval first reached 80% / 90%. This is the
-- answer to "how fast do vehicles earn reliability" in terms of evidence
-- rather than a point estimate. Null means the vehicle has not got there.
--
-- is_active: flew in the 24 months before the latest launch in the data.
--
-- expected_successes: how many successes a typical vehicle would have
-- logged over the same flights, given where each flight sat in its life
-- (flight band) and the vehicle's era. It is the debut curve applied
-- flight by flight, leave-one-out: the vehicle's own flights are removed
-- from the benchmark, so Soyuz is not compared with itself. Where the
-- vehicle is alone in its era for a band, the all-era rate is used.
-- reliability_vs_expected is the gap in reliability points: positive
-- means ahead of a typical vehicle at the same stage of life.

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

band_totals as (

    select
        lens,
        era,
        flight_band_start,
        count(*)                                              as attempts,
        sum(case when outcome = 'success' then 1 else 0 end)  as successes
    from maturation
    group by lens, era, flight_band_start

),

band_totals_all_eras as (

    select
        lens,
        flight_band_start,
        count(*)                                              as attempts,
        sum(case when outcome = 'success' then 1 else 0 end)  as successes
    from maturation
    group by lens, flight_band_start

),

unit_bands as (

    select
        lens,
        unit_key,
        era,
        flight_band_start,
        count(*)                                              as attempts,
        sum(case when outcome = 'success' then 1 else 0 end)  as successes
    from maturation
    group by lens, unit_key, era, flight_band_start

),

expected as (

    select
        u.lens,
        u.unit_key,
        sum(
            u.attempts * coalesce(
                cast(e.successes - u.successes as double) / nullif(e.attempts - u.attempts, 0),
                cast(a.successes - u.successes as double) / nullif(a.attempts - u.attempts, 0)
            )
        ) as expected_successes
    from unit_bands u
    join band_totals e
        on u.lens = e.lens
        and u.era = e.era
        and u.flight_band_start = e.flight_band_start
    join band_totals_all_eras a
        on u.lens = a.lens
        and u.flight_band_start = a.flight_band_start
    group by u.lens, u.unit_key

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
    l.era,
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
    x.expected_successes,
    x.expected_successes / l.flight_number            as expected_reliability,
    l.cum_reliability - x.expected_successes / l.flight_number as reliability_vs_expected,
    m.latest_flight_at >= a.data_as_of - interval 730 days   as is_active,
    a.data_as_of

from latest l
join milestones m
    on l.lens = m.lens
    and l.unit_key = m.unit_key
join expected x
    on l.lens = x.lens
    and l.unit_key = x.unit_key
cross join as_of a
