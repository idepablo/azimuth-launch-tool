-- Orbit dimension, derived from orbits observed in launch data.
-- Includes an explicit "Not published" member (-1) so launches with
-- no orbit stay visible in orbit-class views instead of dropping
-- out of joins. See docs/scope.md on the coverage gap.
-- Classes group ~29 source orbits into analytic buckets. Default
-- (else) is Beyond Earth: new source orbits are more likely new
-- deep-space targets than new Earth regimes.

with observed as (

    select distinct
        orbit_id,
        orbit_name
    from {{ ref('stg_launches') }}
    where orbit_id is not null

),

with_unknown_member as (

    select orbit_id, orbit_name from observed
    union all
    select '-1', 'Not published'

)

select
    orbit_id   as orbit_key,
    orbit_name,

    case
        when orbit_id = '-1'                          then 'Not published'
        when orbit_name = 'Unknown'                   then 'Unknown'
        when orbit_name = 'Suborbital'                then 'Suborbital'
        when orbit_name in ('Low Earth Orbit',
                            'Sun-Synchronous Orbit',
                            'Polar Orbit',
                            'Elliptical Orbit')       then 'LEO class'
        when orbit_name like 'Medium Earth%'
          or orbit_name like 'Semi-Synchronous%'      then 'MEO class'
        when orbit_name like 'Geo%'
          or orbit_name like 'Supersynchronous%'
          or orbit_name like 'Enhanced Geo%'
          or orbit_name = 'High Earth Orbit'          then 'GEO and high Earth'
        -- everything else: lunar, planetary, heliocentric, Lagrange,
        -- asteroid, escape, and Earth Entry Trajectory (the lunar
        -- sample-return ascents, already scope-excluded)
        else 'Beyond Earth orbit'
    end as orbit_class

from with_unknown_member