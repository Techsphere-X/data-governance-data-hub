from src.database import get_connection


FARMS = [
    {
        "farm_name": "Himalayan Harvest Farm",
        "location": "Kathmandu Valley",
        "area_hectares": 25.5,
    },
    {
        "farm_name": "Green Valley Farm",
        "location": "Chitwan",
        "area_hectares": 40.0,
    },
    {
    "farm_name": "Terai Organic Farm",
    "location": "Biratnagar",
    "area_hectares": 30.0,
    },
    {
        "farm_name": "Mountain Fresh Farm",
        "location": "Pokhara",
        "area_hectares": 18.75,
    },
]


def generate_farms():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            inserted = 0
            skipped = 0

            for farm in FARMS:

                # Check whether the farm already exists
                cursor.execute(
                    """
                    SELECT farm_id
                    FROM farm_source.farms
                    WHERE farm_name = %s;
                    """,
                    (farm["farm_name"],),
                )

                existing_farm = cursor.fetchone()

                if existing_farm:
                    skipped += 1
                    continue

                # Insert only if the farm does not exist
                cursor.execute(
                    """
                    INSERT INTO farm_source.farms
                        (
                            farm_name,
                            location,
                            area_hectares
                        )
                    VALUES
                        (%s, %s, %s);
                    """,
                    (
                        farm["farm_name"],
                        farm["location"],
                        farm["area_hectares"],
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
    generate_farms()