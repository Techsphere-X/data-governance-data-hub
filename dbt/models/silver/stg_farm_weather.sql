
with source as (

    select *
    from {{ source('farm_raw', 'weather') }}

),

cleaned as (

    select
        weather_id,
        nullif(trim(location), '') as location,
        recorded_at,
        temperature_c,
        humidity_percent,
        precipitation_mm,
        wind_speed_kmh,
        created_at

    from source

)

select *
from cleaned