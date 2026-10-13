
with source as (

    select *
    from {{ source('farm_raw', 'order_items') }}

),

cleaned as (

    select
        order_item_id,
        order_id,
        product_id,
        quantity,
        unit_price,
        created_at

    from source

)

select *
from cleaned