-- A Kaplan-Meier curve never rises, stays inside [0, 1], and its band
-- brackets the estimate.
with curve as (
    select
        *,
        lag(survival) over (
            partition by lens, era
            order by flight_number
        ) as previous_survival
    from {{ ref('mart_failure_free_survival') }}
)
select lens, era, flight_number, survival, previous_survival
from curve
where survival > previous_survival + 1e-12
   or survival < 0 or survival > 1
   or survival_lower_95 > survival + 1e-12
   or survival_upper_95 < survival - 1e-12
