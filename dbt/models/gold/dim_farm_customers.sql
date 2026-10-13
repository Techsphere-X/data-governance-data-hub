-- One row per customer, ready for sales and customer analysis.
select
    customer_id,
    customer_name,
    email,
    city,
    created_at
from {{ ref('stg_farm_customers') }}