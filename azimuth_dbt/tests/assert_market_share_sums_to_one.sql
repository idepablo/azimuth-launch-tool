-- Within each year, provider shares of attempts add up to 1.
select launch_year, sum(share_of_attempts) as total_share
from {{ ref('mart_market_share_yearly') }}
group by launch_year
having abs(sum(share_of_attempts) - 1) > 1e-9
