from src.database import get_connection


CROPS = [
    {
        "crop_name": "Wheat",
        "crop_type": "Grain",
        "growing_days": 120,
    },
    {
        "crop_name": "Rice",
        "crop_type": "Grain",
        "growing_days": 150,
    },
    {
        "crop_name": "Tomato",
        "crop_type": "Vegetable",
        "growing_days": 90,
    },
    {
        "crop_name": "Potato",
        "crop_type": "Root Vegetable",
        "growing_days": 100,
    },
    {
        "crop_name": "Carrot",
        "crop_type": "Root Vegetable",
        "growing_days": 75,
    },
    {
        "crop_name": "Cabbage",
        "crop_type": "Vegetable",
        "growing_days": 80,
    },
]


def generate_crops():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            inserted = 0
            skipped = 0

            for crop in CROPS:

                cursor.execute(
                    """
                    SELECT crop_id
                    FROM farm_source.crops
                    WHERE crop_name = %s;
                    """,
                    (crop["crop_name"],),
                )

                existing_crop = cursor.fetchone()

                if existing_crop:
                    skipped += 1
                    continue

                cursor.execute(
                    """
                    INSERT INTO farm_source.crops
                        (
                            crop_name,
                            crop_type,
                            growing_days
                        )
                    VALUES
                        (%s, %s, %s);
                    """,
                    (
                        crop["crop_name"],
                        crop["crop_type"],
                        crop["growing_days"],
                    ),
                )

                inserted += 1

        connection.commit()

        print(f"Inserted: {inserted}")
        print(f"Skipped:  {skipped}")
        print(f"Total:    {inserted + skipped}")

    finally:
        connection.close()


if __name__ == "__main__":
    generate_crops()
