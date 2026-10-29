
with source_data as (

    select *
    from {{ source('raw_olist_weather', 'porto') }}

),

ranked as (

    select
        date::date as weather_date,
        station,
        datatype,
        value::numeric as value,
        attributes,

        row_number() over (
            partition by station, date::date, datatype
            order by _airbyte_extracted_at desc
        ) as row_num

    from source_data

)

select
    weather_date,
    station,
    datatype,
    value,
    attributes
from ranked
where row_num = 1