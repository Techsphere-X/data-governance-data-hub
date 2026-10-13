from faker import Faker

from src.database import get_connection


fake = Faker()

CUSTOMER_COUNT = 10


def generate_customers(count=CUSTOMER_COUNT):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            inserted = 0

            while inserted < count:

                customer_name = fake.name()
                email = fake.unique.email()
                city = fake.city()

                # Check whether the email already exists
                cursor.execute(
                    """
                    SELECT customer_id
                    FROM farm_source.customers
                    WHERE email = %s;
                    """,
                    (email,),
                )

                existing_customer = cursor.fetchone()

                if existing_customer:
                    continue

                cursor.execute(
                    """
                    INSERT INTO farm_source.customers
                        (
                            customer_name,
                            email,
                            city
                        )
                    VALUES
                        (%s, %s, %s);
                    """,
                    (
                        customer_name,
                        email,
                        city,
                    ),
                )

                inserted += 1

        connection.commit()

        print(f"Inserted: {inserted}")

    finally:
        connection.close()


if __name__ == "__main__":
    generate_customers()
