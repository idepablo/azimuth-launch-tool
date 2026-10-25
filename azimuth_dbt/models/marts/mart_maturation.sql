-- The maturation dataset: one row per orbital launch attempt per lens,
-- numbered by flight in the vehicle's life, with cumulative reliability
-- and a 95% Wilson score interval.
--
-- Two lenses, unioned:
--   configuration: each launcher configuration is its own vehicle
--                  (Falcon 9 Block 5 starts at flight 1)
--   family:        configurations grouped by vehicle family
--                  (Falcon 9 starts at its 2010 first flight)
-- The family lens is the honest comparable for a new vehicle, because
-- iterated configurations inherit their predecessors' learning.
--
-- Reliability here is strict: successes / attempts. Partial failures are
-- not successes, and are counted separately so views can show them.
--
-- Why Wilson and not successes / attempts alone: a vehicle with 3 of 3
-- has a point estimate of 100% that says almost nothing. The interval
-- widens when there is little evidence and narrows as flights accumulate.
-- A perfect record needs about 35 flights before the lower bound reaches
-- 90%, which is itself an answer to how fast vehicles earn reliability.

with launches as (

    select * from {{ ref('fct_launches') }}

),

vehicles as (

    select * from {{ ref('dim_vehicle') }}

),

orbital as (

    select
        l.launch_id,
        l.launch_name,
        l.launched_at,
        l.status_id,
        l.vehicle_key,
        v.vehicle_full_name,
        v.family_name
    from launches l
    join vehicles v
        on l.vehicle_key = v.vehicle_key
    where l.scope_class = 'orbital'
      and l.is_outcome_known

),

by_lens as (

    select
        'configuration'       as lens,
        vehicle_key           as unit_key,
        vehicle_full_name     as unit_name,
        launch_id,
        launch_name,
        launched_at,
        status_id
    from orbital

    union all

    select
        'family'              as lens,
        family_name           as unit_key,
        family_name           as unit_name,
        launch_id,
        launch_name,
        launched_at,
        status_id
    from orbital

),

numbered as (

    select
        *,
        case
            when status_id in ('3', '9') then 'success'
            when status_id = '4' then 'failure'
            when status_id = '7' then 'partial_failure'
        end as outcome,
        row_number() over (
            partition by lens, unit_key
            order by launched_at, launch_id
        ) as flight_number
    from by_lens

),

cumulative as (

    select
        *,
        sum(case when outcome = 'success' then 1 else 0 end) over (
            partition by lens, unit_key
            order by flight_number
            rows between unbounded preceding and current row
        ) as cum_successes,
        sum(case when outcome = 'failure' then 1 else 0 end) over (
            partition by lens, unit_key
            order by flight_number
            rows between unbounded preceding and current row
        ) as cum_failures,
        sum(case when outcome = 'partial_failure' then 1 else 0 end) over (
            partition by lens, unit_key
            order by flight_number
            rows between unbounded preceding and current row
        ) as cum_partial_failures
    from numbered

),

scored as (

    select
        *,
        cast(cum_successes as double) / flight_number   as cum_reliability,
        1.96                                            as z
    from cumulative

)

select
    lens,
    unit_key,
    unit_name,
    flight_number,
    launch_id,
    launch_name,
    launched_at,
    outcome,
    cum_successes,
    cum_failures,
    cum_partial_failures,
    cum_reliability,
    -- Wilson score interval, 95%. Clamped to [0, 1] because floating
    -- point lands a perfect record's upper bound at 1.0000000000000002.
    greatest(0.0, (
        cum_reliability + z * z / (2 * flight_number)
        - z * sqrt(cum_reliability * (1 - cum_reliability) / flight_number
                   + z * z / (4 * flight_number * flight_number))
    ) / (1 + z * z / flight_number))                    as reliability_lower_95,
    least(1.0, (
        cum_reliability + z * z / (2 * flight_number)
        + z * sqrt(cum_reliability * (1 - cum_reliability) / flight_number
                   + z * z / (4 * flight_number * flight_number))
    ) / (1 + z * z / flight_number))                    as reliability_upper_95

from scored
