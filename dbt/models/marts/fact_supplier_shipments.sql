
{{ config(materialized='table') }}

select
    s.shipment_id,
    s.product_id,
    s.supplier_id,

    s.shipment_date,
    s.quantity,
    s.expected_delivery_date,
    s.actual_delivery_date,
    s.shipment_status,
    s.updated_at,

    s.delivery_days,
    s.delay_days,
    s.is_delivered,
    s.is_status_delayed,
    s.is_date_delayed,
    s.is_delayed,
    s.is_on_time,

    p.product_category_name,
    pc.product_category_name_english

from {{ ref('int_supplier_shipments') }} s

left join {{ ref('stg_products') }} p
    on s.product_id = p.product_id

left join {{ ref('stg_product_categories') }} pc
    on p.product_category_name = pc.product_category_name