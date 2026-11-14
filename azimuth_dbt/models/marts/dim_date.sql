-- Date dimension, generated from SQL rather than source data.
-- Spans the full launch history with headroom on both ends.

with dates as (

    {{ date_spine('1957-01-01', '2030-12-31') }}

)

select
    -- yyyymmdd integer, the conventional date dimension key
    {{ date_key('date_day') }} as date_key,

    date_day,
    year(date_day)                                 as year,
    quarter(date_day)                              as quarter,
    month(date_day)                                as month,
    {{ month_name('date_day') }} as month_name,
    day(date_day)                                  as day_of_month,
    {{ day_name('date_day') }} as day_name,
    {{ is_weekend('date_day') }} as is_weekend,
    -- decade as a label, matching how the analysis talks about eras
    concat(cast(cast(floor(year(date_day) / 10) * 10 as int) as string), 's') as decade

from dates