
SELECT
    order_id,
    payment_record_number,
    COUNT(*) AS row_count
FROM {{ ref('fact_payments') }}
GROUP BY
    order_id,
    payment_record_number
HAVING COUNT(*) > 1