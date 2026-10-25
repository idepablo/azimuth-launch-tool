-- Survival curve for a vehicle's opening run: the probability that a
-- vehicle flies its first n flights without a single failure.
-- Kaplan-Meier estimator, one row per lens, era and flight number at
-- which some vehicle's opening run ended.
--
-- The event is the first flight that was not a full success (failure or
-- partial failure, consistent with strict reliability). A vehicle that has
-- never failed is censored at its latest flight: it is known to have
-- survived that far and no further. That is the point of using
-- Kaplan-Meier rather than a plain average, which would treat a vehicle
-- with three clean flights as if it would never fail.
--
-- Confidence band: 95%, Greenwood's variance on the log-log scale (the
-- default in standard survival libraries; it keeps the band inside
-- [0, 1] without clamping). Verified against Python lifelines.

with maturation as (

    select * from {{ ref('mart_maturation') }}

),

units as (

    select
        lens,
        unit_key,
        era,
        max(flight_number)                                        as flights,
        min(case when outcome <> 'success' then flight_number end) as first_nonsuccess_flight
    from maturation
    group by lens, unit_key, era

),

with_all_eras as (

    select lens, era, unit_key, flights, first_nonsuccess_flight from units
    union all
    select lens, 'all' as era, unit_key, flights, first_nonsuccess_flight from units

),

-- where each vehicle leaves the risk set, and whether it left by failing
exits as (

    select
        lens,
        era,
        coalesce(first_nonsuccess_flight, flights)            as flight_number,
        sum(case when first_nonsuccess_flight is not null then 1 else 0 end) as first_failures,
        sum(case when first_nonsuccess_flight is null then 1 else 0 end)     as censored,
        count(*)                                               as leaving
    from with_all_eras
    group by lens, era, coalesce(first_nonsuccess_flight, flights)

),

-- vehicles still in their opening run at each exit point: everyone who
-- leaves at this flight or later
at_risk as (

    select
        *,
        sum(leaving) over (
            partition by lens, era
            order by flight_number desc
            rows between unbounded preceding and current row
        ) as vehicles_at_risk
    from exits

),

steps as (

    select
        *,
        case
            when first_failures < vehicles_at_risk
                then ln(1 - cast(first_failures as double) / vehicles_at_risk)
        end as log_step,
        case
            when first_failures < vehicles_at_risk
                then cast(first_failures as double)
                     / (vehicles_at_risk * (vehicles_at_risk - first_failures))
        end as greenwood_step,
        case when first_failures = vehicles_at_risk then 1 else 0 end as is_wipeout
    from at_risk

),

curve as (

    select
        lens,
        era,
        flight_number,
        vehicles_at_risk,
        first_failures,
        censored,
        -- once every remaining vehicle has failed, survival is zero
        case
            when max(is_wipeout) over w = 1 then 0.0
            else exp(coalesce(sum(log_step) over w, 0.0))
        end as survival,
        coalesce(sum(greenwood_step) over w, 0.0) as greenwood_sum
    from steps
    window w as (
        partition by lens, era
        order by flight_number
        rows between unbounded preceding and current row
    )

)

select
    lens,
    era,
    flight_number,
    vehicles_at_risk,
    first_failures,
    censored,
    survival,
    -- log-log band: S ^ exp(+/- z * sqrt(V) / |ln S|). Undefined where
    -- survival is exactly 1 (no failures yet) or 0, so set it directly.
    case
        when survival >= 1.0 then 1.0
        when survival <= 0.0 then 0.0
        else power(survival, exp(1.96 * sqrt(greenwood_sum) / abs(ln(survival))))
    end as survival_lower_95,
    case
        when survival >= 1.0 then 1.0
        when survival <= 0.0 then 0.0
        else power(survival, exp(-1.96 * sqrt(greenwood_sum) / abs(ln(survival))))
    end as survival_upper_95
from curve
