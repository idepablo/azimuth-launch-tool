-- Market share by launch count: one row per year and provider.
--
-- Share by mass to orbit is deliberately absent: payload mass is not
-- confirmed obtainable from the source (see docs/scope.md).
--
-- Two shares are reported. Share of attempts measures activity; share of
-- successes measures delivered launches. A provider with many failures
-- ranks lower on the second.

with cadence as (

    select * from {{ ref('mart_cadence_yearly') }}

),

year_totals as (

    select
        launch_year,
        sum(attempts)  as year_attempts,
        sum(successes) as year_successes
    from cadence
    group by launch_year

)

select
    c.launch_year,
    c.provider_key,
    c.provider_name,
    c.country,
    c.sector,
    c.attempts,
    c.successes,
    t.year_attempts,
    t.year_successes,
    cast(c.attempts as double) / t.year_attempts                     as share_of_attempts,
    case
        when t.year_successes > 0
        then cast(c.successes as double) / t.year_successes
    end                                                              as share_of_successes,
    rank() over (
        partition by c.launch_year
        order by c.attempts desc
    )                                                                as rank_by_attempts,
    c.is_partial_year,
    c.data_as_of

from cadence c
join year_totals t
    on c.launch_year = t.launch_year
