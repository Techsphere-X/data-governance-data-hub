{{ config(materialized='view') }}

select
    shipment_id,
    product_id,
    supplier_id,
    shipment_date,
    quantity,
    expected_delivery_date,
    actual_delivery_date,
    shipment_status,
    updated_at,

    case
        when actual_delivery_date is not null
        then actual_delivery_date - shipment_date
    end as delivery_days,

    case
        when actual_delivery_date is not null
             and actual_delivery_date > expected_delivery_date
        then actual_delivery_date - expected_delivery_date
        else 0
    end as delay_days,

    case
        when actual_delivery_date is not null
        then true
        else false
    end as is_delivered,

    case
        when shipment_status = 'Delayed'
        then true
        else false
    end as is_status_delayed,

    case
        when actual_delivery_date is not null
             and actual_delivery_date > expected_delivery_date
        then true
        else false
    end as is_date_delayed,

    case
        when shipment_status = 'Delayed'
             or (
                 actual_delivery_date is not null
                 and actual_delivery_date > expected_delivery_date
             )
        then true
        else false
    end as is_delayed,

    case
        when actual_delivery_date is not null
             and actual_delivery_date <= expected_delivery_date
        then true
        else false
    end as is_on_time

from {{ ref('stg_supplier_shipments') }}
