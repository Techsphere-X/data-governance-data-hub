from src.database import get_connection


FIELDS = [
    {
        "farm_name": "Himalayan Harvest Farm",
        "field_name": "Field A",
        "area_hectares": 8.5,
        "soil_type": "Loamy",
    },
    {
        "farm_name": "Himalayan Harvest Farm",
        "field_name": "Field B",
        "area_hectares": 7.0,
        "soil_type": "Clay",
    },
    {
        "farm_name": "Himalayan Harvest Farm",
        "field_name": "Field C",
        "area_hectares": 10.0,
        "soil_type": "Sandy Loam",
    },
    {
        "farm_name": "Green Valley Farm",
        "field_name": "Field A",
        "area_hectares": 20.0,
        "soil_type": "Loamy",
    },
    {
        "farm_name": "Green Valley Farm",
        "field_name": "Field B",
        "area_hectares": 20.0,
        "soil_type": "Clay",
    },
    {
        "farm_name": "Mountain Fresh Farm",
        "field_name": "Field A",
        "area_hectares": 9.0,
        "soil_type": "Loamy",
    },
    {
        "farm_name": "Mountain Fresh Farm",
        "field_name": "Field B",
        "area_hectares": 9.75,
        "soil_type": "Sandy Loam",
    },
]


def generate_fields():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            inserted = 0
            skipped = 0

            for field in FIELDS:

                # Find the parent farm
                cursor.execute(
                    """
                    SELECT farm_id
                    FROM farm_source.farms
                    WHERE farm_name = %s;
                    """,
                    (field["farm_name"],),
                )

                result = cursor.fetchone()

                if result is None:
                    raise ValueError(
                        f"Farm not found: {field['farm_name']}"
                    )

                farm_id = result[0]

                # Check whether this field already exists
                cursor.execute(
                    """
                    SELECT field_id
                    FROM farm_source.fields
                    WHERE farm_id = %s
                      AND field_name = %s;
                    """,
                    (
                        farm_id,
                        field["field_name"],
                    ),
                )

                existing_field = cursor.fetchone()

                if existing_field:
                    skipped += 1
                    continue

                cursor.execute(
                    """
                    INSERT INTO farm_source.fields
                        (
                            farm_id,
                            field_name,
                            area_hectares,
                            soil_type
                        )
                    VALUES
                        (%s, %s, %s, %s);
                    """,
                    (
                        farm_id,
                        field["field_name"],
                        field["area_hectares"],
                        field["soil_type"],
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
    generate_fields()
