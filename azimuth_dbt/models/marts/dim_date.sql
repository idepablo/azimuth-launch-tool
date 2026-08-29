-- Date dimension, generated from SQL rather than source data.
-- Spans the full launch history with headroom on both ends.

with dates as (

    select explode(sequence(
        to_date('1957-01-01'),
        to_date('2030-12-31'),
        interval 1 day
    )) as date_day

)

select
    -- yyyymmdd integer, the conventional date dimension key
    cast(date_format(date_day, 'yyyyMMdd') as int) as date_key,

    date_day,
    year(date_day)                                 as year,
    quarter(date_day)                              as quarter,
    month(date_day)                                as month,
    date_format(date_day, 'MMMM')                  as month_name,
    day(date_day)                                  as day_of_month,
    date_format(date_day, 'EEEE')                  as day_name,
    weekday(date_day) >= 5                         as is_weekend,
    -- decade as a label, matching how the analysis talks about eras
    concat(cast(floor(year(date_day) / 10) * 10 as string), 's') as decade

from dates