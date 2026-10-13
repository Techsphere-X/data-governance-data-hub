
with weather as (

    select
        weather_id,
        location,
        recorded_at,
        temperature_c,
        humidity_percent,
        precipitation_mm,
        wind_speed_kmh

    from {{ ref('stg_farm_weather') }}

),

daily_weather as (

    select
        location,
        cast(recorded_at as date) as weather_date,

        count(*) as weather_observation_count,

        round(avg(temperature_c)::numeric, 2)
            as average_temperature_c,

        round(min(temperature_c)::numeric, 2)
            as minimum_temperature_c,

        round(max(temperature_c)::numeric, 2)
            as maximum_temperature_c,

        round(avg(humidity_percent)::numeric, 2)
            as average_humidity_percent,

        round(sum(precipitation_mm)::numeric, 2)
            as total_precipitation_mm,

        round(avg(wind_speed_kmh)::numeric, 2)
            as average_wind_speed_kmh

    from weather
    group by
        location,
        cast(recorded_at as date)

)

select *
from daily_weather