-- Provider dimension, derived from launch data.
-- NOTE: country and sector require the agencies endpoint, not yet
-- ingested. They join this model when that load exists.

with launches as (

    select * from {{ ref('stg_launches') }}

)

select
    provider_id                                   as provider_key,
    provider_name,
    min(launched_at)                              as first_launch_at,
    max(launched_at)                              as latest_launch_at,
    count(*)                                      as launch_count

from launches
group by 1, 2