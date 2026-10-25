-- The debut curve: how likely is a vehicle's flight to succeed, given how
-- far into its life the vehicle is? One row per lens, era and flight band.
--
-- This is a discrete-time hazard estimate. At each flight band, the
-- vehicles "at risk" are the ones that got that far, and the success rate
-- is measured among those flights only. Vehicles that retire early simply
-- stop contributing, which is how censoring is handled.
--
-- One caveat belongs on the methodology page: retirement is not random.
-- Vehicles that fail a lot tend to be cancelled, so late bands are made of
-- the survivors. The curve describes vehicles that made it that far, not
-- a promise that any vehicle will improve on schedule.
--
-- era = 'all' pools every era, and is what the Scenario Simulator uses
-- when an era-specific band is too thin.

with maturation as (

    select * from {{ ref('mart_maturation') }}

),

with_all_eras as (

    select lens, era, flight_band_start, flight_band, unit_key, outcome
    from maturation

    union all

    select lens, 'all' as era, flight_band_start, flight_band, unit_key, outcome
    from maturation

),

aggregated as (

    select
        lens,
        era,
        flight_band_start,
        flight_band,
        count(distinct unit_key)                                      as vehicles,
        count(*)                                                      as attempts,
        sum(case when outcome = 'success' then 1 else 0 end)          as successes,
        sum(case when outcome = 'failure' then 1 else 0 end)          as failures,
        sum(case when outcome = 'partial_failure' then 1 else 0 end)  as partial_failures
    from with_all_eras
    group by lens, era, flight_band_start, flight_band

),

scored as (

    select
        *,
        cast(successes as double) / attempts  as success_rate,
        1.96                                  as z
    from aggregated

)

select
    lens,
    era,
    flight_band_start,
    flight_band,
    vehicles,
    attempts,
    successes,
    failures,
    partial_failures,
    success_rate,
    -- 95% Wilson score interval, same formula as mart_maturation
    greatest(0.0, (
        success_rate + z * z / (2 * attempts)
        - z * sqrt(success_rate * (1 - success_rate) / attempts
                   + z * z / (4 * attempts * attempts))
    ) / (1 + z * z / attempts))               as success_rate_lower_95,
    least(1.0, (
        success_rate + z * z / (2 * attempts)
        + z * sqrt(success_rate * (1 - success_rate) / attempts
                   + z * z / (4 * attempts * attempts))
    ) / (1 + z * z / attempts))               as success_rate_upper_95

from scored
