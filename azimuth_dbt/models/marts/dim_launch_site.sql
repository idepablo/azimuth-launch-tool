-- Launch site dimension: one row per location (site), e.g. Cape
-- Canaveral SFS. Pads are finer-grained and stay on the fact as
-- degenerate attributes (pad_name); several pads roll up to one site.
-- Coordinates are the centroid of the site's pad coordinates, an
-- approximation good enough for mapping.

with launches as (

    select * from {{ ref('stg_launches') }}

)

select
    location_id                       as location_key,
    location_name,
    location_country                  as country,
    location_country_code             as country_code,
    celestial_body,
    avg(pad_latitude)                 as site_latitude,
    avg(pad_longitude)                as site_longitude,
    count(distinct pad_id)            as pad_count,
    min(launched_at)                  as first_launch_at,
    max(launched_at)                  as latest_launch_at,
    count(*)                          as launch_count

from launches
group by 1, 2, 3, 4, 5