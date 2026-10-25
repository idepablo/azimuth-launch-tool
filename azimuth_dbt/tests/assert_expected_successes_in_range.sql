-- The maturity-adjusted benchmark is a count of expected successes over
-- the vehicle's own flights, so it must sit between 0 and its flights.
select lens, unit_key, flights, expected_successes
from {{ ref('mart_vehicle_reliability') }}
where expected_successes < 0
   or expected_successes > flights
