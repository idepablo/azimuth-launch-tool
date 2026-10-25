-- Each vehicle (per lens) has exactly one row per flight number,
-- and flight numbers run 1..n with no gaps.
select lens, unit_key, flight_number
from {{ ref('mart_maturation') }}
group by lens, unit_key, flight_number
having count(*) > 1

union all

select lens, unit_key, max(flight_number)
from {{ ref('mart_maturation') }}
group by lens, unit_key
having max(flight_number) <> count(*)
