
with products as (

    select *
    from {{ ref('stg_farm_products') }}

),

order_items as (

    select *
    from {{ ref('stg_farm_order_items') }}

),

product_metrics as (

    select
        product_id,
        count(distinct order_id) as total_orders,
        coalesce(sum(quantity), 0) as total_quantity_ordered,
        coalesce(
            sum(quantity * unit_price),
            0
        ) as total_ordered_amount,
        avg(unit_price) as average_order_item_unit_price

    from order_items
    group by product_id

)

select
    p.product_id,
    p.product_name,
    p.crop_id,
    p.unit,
    p.unit_price as catalog_unit_price,

    coalesce(pm.total_orders, 0) as total_orders,
    coalesce(pm.total_quantity_ordered, 0) as total_quantity_ordered,
    coalesce(pm.total_ordered_amount, 0) as total_ordered_amount,
    pm.average_order_item_unit_price,

    p.created_at

from products p

left join product_metrics pm
    on p.product_id = pm.product_id