-- One row per launcher configuration that appears in launch data,
-- with its vehicle family resolved from the source hierarchy.
--
-- The source lists a configuration's family plus every ancestor of it:
-- Falcon 9 Block 5 lists "Falcon" (root) and "Falcon 9" (parent: Falcon).
-- So this is a hierarchy, not a many-to-many. The family used for
-- analysis is the most specific one (the leaf); the root is kept as
-- family_root_name for program-level grouping.
--
-- Resolution order:
--   1. reviewed override from seeds/family_overrides.csv
--   2. leaf family from the source hierarchy
--   3. fallback: the configuration's own name (vehicles the source
--      gives no family, such as Space Shuttle or Electron)

with families as (

    select
        config_id,
        family_name,
        parent_family_name
    from {{ source('bronze', 'launcher_families') }}

),

-- a family is a leaf for a configuration when no other family listed
-- for that same configuration names it as parent
leaves as (

    select
        f.config_id,
        f.family_name,
        f.parent_family_name
    from families f
    left join families child
        on child.config_id = f.config_id
        and child.parent_family_name = f.family_name
    where child.config_id is null

),

-- tie-break for the rare case of two leaves (the source lists Minotaur
-- and Minotaur-C as separate roots for the Minotaur-C configurations):
-- prefer a family that has a parent, then the longer, more specific name
ranked_leaves as (

    select
        config_id,
        family_name,
        row_number() over (
            partition by config_id
            order by
                case when parent_family_name is null then 1 else 0 end,
                length(family_name) desc,
                family_name
        ) as leaf_rank
    from leaves

),

roots as (

    select
        config_id,
        min(family_name) as family_root_name
    from families
    where parent_family_name is null
    group by config_id

),

overrides as (

    select
        cast(config_id as string) as config_id,
        family_name
    from {{ ref('family_overrides') }}

),

configs as (

    select distinct
        config_id,
        config_name
    from {{ ref('stg_launches') }}

)

select
    c.config_id,
    c.config_name,
    coalesce(o.family_name, l.family_name, c.config_name)    as family_name,
    coalesce(r.family_root_name, o.family_name, l.family_name, c.config_name)
                                                             as family_root_name,
    case
        when o.family_name is not null then 'override'
        when l.family_name is not null then 'source'
        else 'fallback_config_name'
    end                                                      as family_source

from configs c
left join ranked_leaves l
    on l.config_id = c.config_id
    and l.leaf_rank = 1
left join roots r
    on r.config_id = c.config_id
left join overrides o
    on o.config_id = c.config_id
