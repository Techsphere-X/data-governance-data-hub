import random
from decimal import Decimal

from src.database import get_connection


ORDER_COUNT = 10

ORDER_STATUSES = [
    "pending",
    "confirmed",
    "completed",
    "cancelled",
]


def generate_orders(count=ORDER_COUNT):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            # Get existing customers
            cursor.execute(
                """
                SELECT customer_id
                FROM farm_source.customers;
                """
            )

            customers = [row[0] for row in cursor.fetchall()]

            if not customers:
                raise ValueError(
                    "No customers found. Generate customers first."
                )

            inserted = 0

            for _ in range(count):

                customer_id = random.choice(customers)

                status = random.choice(ORDER_STATUSES)

                total_amount = Decimal(
                    str(round(random.uniform(500, 10000), 2))
                )

                cursor.execute(
                    """
                    INSERT INTO farm_source.orders
                        (
                            customer_id,
                            status,
                            total_amount
                        )
                    VALUES
                        (%s, %s, %s);
                    """,
                    (
                        customer_id,
                        status,
                        total_amount,
                    ),
                )

                inserted += 1

        connection.commit()

        print(f"Inserted: {inserted}")

    finally:
        connection.close()


if __name__ == "__main__":
    generate_orders()
