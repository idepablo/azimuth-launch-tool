-- Vehicle dimension: one row per launcher configuration.
-- Classification comes from the curated seed. Display names are the
-- API's shared names: several configurations can share one name
-- (Falcon 9 covers five). full_name/variant require the configurations
-- endpoint, not yet ingested; they join this model when that load exists.

with launches as (

    select * from {{ ref('stg_launches') }}

),

classification as (

    select * from {{ ref('vehicle_classification') }}

),

from_launches as (

    select
        config_id                                as vehicle_key,
        config_name                              as vehicle_name,
        min(launched_at)                         as first_launch_at,
        max(launched_at)                         as latest_launch_at,
        count(*)                                 as launch_count

    from launches
    group by 1, 2

)

select
    l.vehicle_key,
    l.vehicle_name,
    c.vehicle_class,
    c.notes                                      as classification_notes,
    l.first_launch_at,
    l.latest_launch_at,
    l.launch_count

from from_launches l
left join classification c
    on l.vehicle_key = c.config_id