
with source as (

    select *
    from {{ source('farm_raw', 'orders') }}

),

cleaned as (

    select
        order_id,
        customer_id,
        order_date,
        nullif(lower(trim(status)), '') as status,
        total_amount,
        created_at

    from source

)

select *
from cleaned