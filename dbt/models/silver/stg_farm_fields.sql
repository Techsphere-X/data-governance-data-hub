
with source as (

    select *
    from {{ source('farm_raw', 'fields') }}

),

cleaned as (

    select
        field_id,
        farm_id,
        nullif(trim(field_name), '') as field_name,
        nullif(lower(trim(soil_type)), '') as soil_type,
        area_hectares,
        created_at

    from source

)

select *
from cleaned