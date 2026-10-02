{{ config(materialized='view') }}

select
    shipment_id,
    product_id,
    supplier_id,

    cast(shipment_date as date) as shipment_date,
    cast(quantity as integer) as quantity,
    cast(expected_delivery_date as date) as expected_delivery_date,
    nullif(actual_delivery_date, '')::date as actual_delivery_date,

    shipment_status,
    cast(updated_at as timestamp) as updated_at

from {{ source('raw_shipment_csv', 'supplier_shipments') }}
