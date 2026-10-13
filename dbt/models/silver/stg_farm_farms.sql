
with source as (

    select *
    from {{ source('farm_raw', 'farms') }}

),

cleaned as (

    select
        farm_id,
        nullif(trim(farm_name), '') as farm_name,
        nullif(trim(location), '') as location,
        area_hectares,
        created_at

    from source

)

select *
from cleaned