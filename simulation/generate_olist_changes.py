import os
import uuid
from datetime import datetime, timedelta

import psycopg2

# ---------------------------------------------------------
# Database configuration
# ---------------------------------------------------------

DB_HOST = os.getenv("DB_HOST", "host.docker.internal")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "olist_raw")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")


# ---------------------------------------------------------
# Generate 5 new Olist records
# ---------------------------------------------------------


def generate_new_records():
    if not DB_PASSWORD:
        raise ValueError("DB_PASSWORD environment variable is not set.")

    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )

    cursor = conn.cursor()

    try:
        now = datetime.now()

        # Get 5 existing products and sellers so we can
        # create realistic order items without creating
        # new products/sellers.
        cursor.execute("""
            SELECT product_id
            FROM public.olist_products
            WHERE product_id IS NOT NULL
            LIMIT 5;
        """)
        products = [row[0] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT seller_id
            FROM public.olist_sellers
            WHERE seller_id IS NOT NULL
            LIMIT 5;
        """)
        sellers = [row[0] for row in cursor.fetchall()]

        if len(products) < 5:
            raise ValueError("Could not find 5 existing products.")

        if len(sellers) < 5:
            raise ValueError("Could not find 5 existing sellers.")

        for i in range(5):

            # ---------------------------------------------
            # IDs
            # ---------------------------------------------

            customer_id = str(uuid.uuid4()).replace("-", "")[:32]
            order_id = str(uuid.uuid4()).replace("-", "")[:32]

            product_id = products[i]
            seller_id = sellers[i]

            # ---------------------------------------------
            # Customer
            # ---------------------------------------------

            cursor.execute(
                """
                INSERT INTO public.olist_customers (
                    customer_id,
                    customer_unique_id,
                    customer_zip_code_prefix,
                    customer_city,
                    customer_state,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s);
            """,
                (
                    customer_id,
                    str(uuid.uuid4()).replace("-", "")[:32],
                    44600 + i,
                    "simulated_city",
                    "SP",
                    now,
                ),
            )

            # ---------------------------------------------
            # Order
            # ---------------------------------------------

            purchase_time = now - timedelta(minutes=i)

            cursor.execute(
                """
                INSERT INTO public.olist_orders (
                    order_id,
                    customer_id,
                    order_status,
                    order_purchase_timestamp,
                    order_approved_at,
                    order_delivered_carrier_date,
                    order_delivered_customer_date,
                    order_estimated_delivery_date,
                    updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                );
            """,
                (
                    order_id,
                    customer_id,
                    "processing",
                    purchase_time,
                    purchase_time,
                    None,
                    None,
                    purchase_time + timedelta(days=10),
                    now,
                ),
            )

            # ---------------------------------------------
            # Order item
            # ---------------------------------------------

            cursor.execute(
                """
                INSERT INTO public.olist_order_items (
                    order_id,
                    order_item_id,
                    product_id,
                    seller_id,
                    shipping_limit_date,
                    price,
                    freight_value,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """,
                (
                    order_id,
                    1,
                    product_id,
                    seller_id,
                    purchase_time + timedelta(days=2),
                    100.00 + i,
                    15.00,
                    now,
                ),
            )

            # ---------------------------------------------
            # Payment
            # ---------------------------------------------

            cursor.execute(
                """
                INSERT INTO public.olist_order_payments (
                    order_id,
                    payment_sequential,
                    payment_type,
                    payment_installments,
                    payment_value,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s);
            """,
                (
                    order_id,
                    1,
                    "credit_card",
                    1,
                    115.00 + i,
                    now,
                ),
            )

            print(f"Created order: {order_id}")

        conn.commit()

        print("\nSuccessfully inserted 5 new orders.")
        print("Each order also has a customer, order item, and payment.")

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    generate_new_records()
