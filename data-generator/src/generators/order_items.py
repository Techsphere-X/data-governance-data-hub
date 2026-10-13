import random
from decimal import Decimal

from src.database import get_connection


ITEMS_PER_ORDER = (1, 3)


def generate_order_items():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            # Get the latest order IDs that do not have items yet
            cursor.execute(
                """
                SELECT o.order_id
                FROM farm_source.orders o
                LEFT JOIN farm_source.order_items oi
                    ON o.order_id = oi.order_id
                WHERE oi.order_item_id IS NULL
                ORDER BY o.order_id;
                """
            )

            orders_without_items = [
                row[0] for row in cursor.fetchall()
            ]

            if not orders_without_items:
                print("No orders without items found.")
                return

            # Get products and prices
            cursor.execute(
                """
                SELECT product_id, unit_price
                FROM farm_source.products;
                """
            )

            products = cursor.fetchall()

            if not products:
                raise ValueError(
                    "No products found. Generate products first."
                )

            inserted = 0

            for order_id in orders_without_items:

                number_of_items = random.randint(
                    ITEMS_PER_ORDER[0],
                    ITEMS_PER_ORDER[1],
                )

                selected_products = random.sample(
                    products,
                    min(number_of_items, len(products)),
                )

                for product_id, unit_price in selected_products:

                    quantity = random.randint(1, 20)

                    cursor.execute(
                        """
                        INSERT INTO farm_source.order_items
                            (
                                order_id,
                                product_id,
                                quantity,
                                unit_price
                            )
                        VALUES
                            (%s, %s, %s, %s);
                        """,
                        (
                            order_id,
                            product_id,
                            quantity,
                            Decimal(str(unit_price)),
                        ),
                    )

                    inserted += 1

        connection.commit()

        print(f"Inserted: {inserted}")

    finally:
        connection.close()


if __name__ == "__main__":
    generate_order_items()
