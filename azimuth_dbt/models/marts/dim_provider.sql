-- Provider dimension, launch-derived aggregates enriched with the
-- agencies reference snapshot (country, sector, founding year).
-- Agency country is a list in the source (multinational agencies);
-- the flatten took the first entry, country_count > 1 flags the rest.

with launches as (

    select * from {{ ref('stg_launches') }}

),

agencies as (

    select * from {{ source('bronze', 'agencies') }}

),

from_launches as (

    select
        provider_id                               as provider_key,
        provider_name,
        min(launched_at)                          as first_launch_at,
        max(launched_at)                          as latest_launch_at,
        count(*)                                  as launch_count

    from launches
    group by 1, 2

)

select
    l.provider_key,
    l.provider_name,
    a.agency_type                                 as sector,
    a.country_name                                as country,
    a.country_code,
    cast(try_cast(a.country_count as double) as int)  as country_count,
    cast(try_cast(a.founding_year as double) as int)  as founding_year,
    l.first_launch_at,
    l.latest_launch_at,
    l.launch_count

from from_launches l
left join agencies a
    on l.provider_key = a.agency_id