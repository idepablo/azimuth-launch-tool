-- The Wilson interval must contain the point estimate and stay in [0, 1].
select *
from {{ ref('mart_maturation') }}
where reliability_lower_95 < 0
   or reliability_upper_95 > 1
   or reliability_lower_95 > cum_reliability + 1e-9
   or reliability_upper_95 < cum_reliability - 1e-9
