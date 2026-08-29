-- Launch fact table: one row per launch attempt (grain = launch_id).
-- Keys join to dim_date, dim_provider, dim_vehicle, dim_orbit.
-- net_precision rides the fact so time-series views can exclude
-- coarse-precision records explicitly (see docs/scope.md).

with launches as (

    select * from {{ ref('stg_launches') }}

)

select
    -- grain
    launch_id,
    launch_name,

    -- dimension keys
    cast(date_format(launched_at, 'yyyyMMdd') as int) as date_key,
    provider_id                                       as provider_key,
    config_id                                         as vehicle_key,
    -- orbit key: nulls map to the dimension's Not published member
    coalesce(orbit_id, '-1')                          as orbit_key,
    location_id                                       as location_key,

    -- degenerate attributes
    launched_at,
    net_precision,
    mission_name,
    orbit_name,
    pad_name,
    status_id,
    status_name,

    -- classification and outcome
    scope_class,
    is_outcome_known,
    is_success,

    -- lineage
    source_file,
    ingest_date

from launches