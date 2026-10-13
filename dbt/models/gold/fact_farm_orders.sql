-- Order-level metrics joined with customer information and aggregated item totals.
with orders as (

    select *
    from {{ ref('stg_farm_orders') }}

),

item_totals as (

    select
        order_id,
        sum(quantity) as total_items,
        sum(quantity * unit_price) as calculated_item_amount,
        count(*) as order_item_count
    from {{ ref('stg_farm_order_items') }}
    group by order_id

)

select
    o.order_id,
    o.customer_id,
    c.customer_name,
    c.city as customer_city,
    o.order_date,
    o.status,
    o.total_amount as order_total_amount,
    coalesce(i.total_items, 0) as total_items,
    coalesce(i.order_item_count, 0) as order_item_count,
    coalesce(i.calculated_item_amount, 0) as calculated_item_amount,
    o.created_at

from orders o
left join {{ ref('stg_farm_customers') }} c
    on o.customer_id = c.customer_id
left join item_totals i
    on o.order_id = i.order_id