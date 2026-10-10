with orders as (


select
    fo.*,
    lower(trim(dc.customer_city)) as customer_city,
    dc.customer_state,

    case
        when lower(trim(dc.customer_city)) = 'sao paulo'
            then 'Sao'
        when lower(trim(dc.customer_city)) = 'rio de janeiro'
            then 'Rio'
        when lower(trim(dc.customer_city)) = 'belo horizonte'
            then 'Belo_Horizonte'
        when lower(trim(dc.customer_city)) = 'curitiba'
            then 'Curitiba'
        else null
    end as weather_station

from {{ ref('fact_orders') }} as fo

left join {{ ref('dim_customers') }} as dc
    on fo.customer_id = dc.customer_id


),

weather_records as (


select
    weather_date,
    'Sao' as weather_station,
    datatype,
    value
from {{ ref('stg_weather_sao') }}

union all

select
    weather_date,
    'Rio' as weather_station,
    datatype,
    value
from {{ ref('stg_weather_rio') }}

union all

select
    weather_date,
    'Belo_Horizonte' as weather_station,
    datatype,
    value
from {{ ref('stg_weather_belo_horizonte') }}

union all

select
    weather_date,
    'Curitiba' as weather_station,
    datatype,
    value
from {{ ref('stg_weather_curitiba') }}


),

daily_weather as (


select
    weather_date,
    weather_station,

    max(case
        when datatype = 'PRCP' then value
    end) as precipitation,

    max(case
        when datatype = 'TAVG' then value
    end) as average_temperature,

    max(case
        when datatype = 'TMIN' then value
    end) as minimum_temperature

from weather_records

group by
    weather_date,
    weather_station


)

select
o.*,
o.order_purchase_at::date as weather_date,
w.precipitation,
w.average_temperature,
w.minimum_temperature

from orders as o

left join daily_weather as w
on o.weather_station = w.weather_station
and o.order_purchase_at::date = w.weather_date
