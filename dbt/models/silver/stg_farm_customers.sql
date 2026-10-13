
with source as (

    select *
    from {{ source('farm_raw', 'customers') }}

),

cleaned as (

    select
        customer_id,
        nullif(trim(customer_name), '') as customer_name,
        nullif(lower(trim(email)), '') as email,
        nullif(trim(city), '') as city,
        created_at::timestamp as created_at

    from source

)

select *
from cleaned