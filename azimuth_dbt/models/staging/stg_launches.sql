-- Staging model for launches.
-- Casts bronze strings into real types, derives the outcome flags,
-- joins the vehicle classification seed, and applies the scoping rule
-- from docs/scope.md.

with source as (

    select * from {{ source('bronze', 'launches') }}

),

classified as (

    select * from {{ ref('vehicle_classification') }}

),

casted as (

    select
        launch_id,
        name as launch_name,

        -- dates: the one real casting job in this table
        cast(net as timestamp) as launched_at,
        net_precision_name    as net_precision,
        cast(last_updated as timestamp) as record_last_updated,

        -- ids stay strings: they are identifiers, not quantities,
        -- and the seed join key is pinned as string
        status_id,
        status_name,
        provider_id,
        provider_name,
        config_id,
        config_name,
                -- orbit_id and mission_id carry a pandas float artifact ('15.0'):
        -- both had nulls in source, so the flatten promoted them to float
        -- before stringifying. Normalize back to clean integer strings.
        cast(cast(try_cast(mission_id as double) as int) as string) as mission_id,
        mission_name,
                cast(cast(try_cast(orbit_id as double) as int) as string) as orbit_id,
        orbit_name,
        pad_id,
        pad_name,
        
        -- location_id shares orbit_id's pandas float artifact (nullable
        -- at flatten time): normalize to clean integer strings
        cast(cast(try_cast(location_id as double) as int) as string) as location_id,
        location_name,
        location_country,
        location_country_code,
        celestial_body,
        cast(pad_latitude as double)  as pad_latitude,
        cast(pad_longitude as double) as pad_longitude,

        -- lineage
        source_file,
        ingest_date

    from source

),

flagged as (

    select
        *,

        -- censoring boundary from scope.md: statuses 3,4,7,9 are outcomes,
        -- everything else is a schedule state
        status_id in ('3', '4', '7', '9') as is_outcome_known,

        -- success is 3 OR 9 (scope.md: both describe a launch that worked)
        case
            when status_id in ('3', '9') then true
            when status_id in ('4', '7') then false
            else null
        end as is_success

    from casted

)

select
    f.*,

    -- vehicle-level classification from the curated seed
    c.vehicle_class,

    -- scoping rule from scope.md: vehicle class is the default,
    -- the per-launch orbit field overrides it where it explicitly
    -- says Suborbital (orbit_id 15), covering mixed-regime configs
    case
        when f.orbit_id = '15' then 'suborbital'
        else coalesce(c.vehicle_class, 'unclassified')
    end as scope_class

from flagged f
left join classified c
    on f.config_id = c.config_id