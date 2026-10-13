import random
from datetime import date, timedelta
from decimal import Decimal

from src.database import get_connection


HARVEST_COUNT = 10

QUALITY_GRADES = [
    "A",
    "B",
    "C",
]


def generate_harvests(count=HARVEST_COUNT):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            # Get existing fields
            cursor.execute(
                """
                SELECT field_id
                FROM farm_source.fields;
                """
            )

            fields = [row[0] for row in cursor.fetchall()]

            if not fields:
                raise ValueError(
                    "No fields found. Generate fields first."
                )

            # Get existing crops
            cursor.execute(
                """
                SELECT crop_id
                FROM farm_source.crops;
                """
            )

            crops = [row[0] for row in cursor.fetchall()]

            if not crops:
                raise ValueError(
                    "No crops found. Generate crops first."
                )

            inserted = 0

            for _ in range(count):

                field_id = random.choice(fields)
                crop_id = random.choice(crops)

                harvest_date = (
                    date.today()
                    - timedelta(days=random.randint(0, 180))
                )

                quantity_kg = Decimal(
                    str(round(random.uniform(100, 5000), 2))
                )

                quality_grade = random.choice(
                    QUALITY_GRADES
                )

                cursor.execute(
                    """
                    INSERT INTO farm_source.harvests
                        (
                            field_id,
                            crop_id,
                            harvest_date,
                            quantity_kg,
                            quality_grade
                        )
                    VALUES
                        (%s, %s, %s, %s, %s);
                    """,
                    (
                        field_id,
                        crop_id,
                        harvest_date,
                        quantity_kg,
                        quality_grade,
                    ),
                )

                inserted += 1

        connection.commit()

        print(f"Inserted: {inserted}")

    finally:
        connection.close()


if __name__ == "__main__":
    generate_harvests()
