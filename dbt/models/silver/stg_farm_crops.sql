
with source as (

    select *
    from {{ source('farm_raw', 'crops') }}

),

cleaned as (

    select
        crop_id,
        nullif(trim(crop_name), '') as crop_name,
        nullif(lower(trim(crop_type)), '') as crop_type,
        growing_days,
        created_at

    from source

)

select *
from cleaned