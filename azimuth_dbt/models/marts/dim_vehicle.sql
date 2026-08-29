-- Vehicle dimension: one row per launcher configuration.
-- Classification from the curated seed; full_name/variant/manufacturer
-- from the configurations reference snapshot. Display names can be
-- shared across configurations (Falcon 9 covers five) — full_name is
-- the disambiguated form. True duplicate records (Soyuz U / Soyuz-U)
-- remain separate ids; canonicalization is deferred until the
-- maturation analysis needs it.

with launches as (

    select * from {{ ref('stg_launches') }}

),

classification as (

    select * from {{ ref('vehicle_classification') }}

),

configurations as (

    select * from {{ source('bronze', 'launcher_configurations') }}

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
    coalesce(cfg.full_name, l.vehicle_name)      as vehicle_full_name,
    cfg.variant,
    cfg.manufacturer_name,
    c.vehicle_class,
    cast(cfg.reusable as boolean)                as is_reusable,
    cast(cfg.maiden_flight as date)              as maiden_flight,
    c.notes                                      as classification_notes,
    l.first_launch_at,
    l.latest_launch_at,
    l.launch_count

from from_launches l
left join classification c
    on l.vehicle_key = c.config_id
left join configurations cfg
    on l.vehicle_key = cfg.config_id