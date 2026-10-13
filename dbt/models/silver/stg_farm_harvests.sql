
with source as (

    select *
    from {{ source('farm_raw', 'harvests') }}

),

cleaned as (

    select
        harvest_id,
        field_id,
        crop_id,
        harvest_date,
        quantity_kg,
        nullif(upper(trim(quality_grade)), '') as quality_grade,
        created_at

    from source

)

select *
from cleaned