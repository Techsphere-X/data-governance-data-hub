
with source as (

    select *
    from {{ source('farm_raw', 'products') }}

),

cleaned as (

    select
        product_id,
        crop_id,
        nullif(trim(product_name), '') as product_name,
        nullif(lower(trim(unit)), '') as unit,
        unit_price,
        created_at

    from source

)

select *
from cleaned