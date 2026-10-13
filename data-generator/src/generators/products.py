from src.database import get_connection


PRODUCTS = [
    {
        "product_name": "Premium Wheat",
        "crop_name": "Wheat",
        "unit_price": 85.00,
        "unit": "kg",
    },
    {
        "product_name": "Himalayan Rice",
        "crop_name": "Rice",
        "unit_price": 120.00,
        "unit": "kg",
    },
    {
        "product_name": "Fresh Tomato",
        "crop_name": "Tomato",
        "unit_price": 140.00,
        "unit": "kg",
    },
    {
        "product_name": "Fresh Potato",
        "crop_name": "Potato",
        "unit_price": 90.00,
        "unit": "kg",
    },
    {
        "product_name": "Organic Carrot",
        "crop_name": "Carrot",
        "unit_price": 110.00,
        "unit": "kg",
    },
    {
        "product_name": "Fresh Cabbage",
        "crop_name": "Cabbage",
        "unit_price": 80.00,
        "unit": "kg",
    },
]


def generate_products():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            inserted = 0
            skipped = 0

            for product in PRODUCTS:

                # Find the parent crop
                cursor.execute(
                    """
                    SELECT crop_id
                    FROM farm_source.crops
                    WHERE crop_name = %s;
                    """,
                    (product["crop_name"],),
                )

                result = cursor.fetchone()

                if result is None:
                    raise ValueError(
                        f"Crop not found: {product['crop_name']}"
                    )

                crop_id = result[0]

                # Check whether product already exists
                cursor.execute(
                    """
                    SELECT product_id
                    FROM farm_source.products
                    WHERE product_name = %s;
                    """,
                    (product["product_name"],),
                )

                existing_product = cursor.fetchone()

                if existing_product:
                    skipped += 1
                    continue

                cursor.execute(
                    """
                    INSERT INTO farm_source.products
                        (
                            product_name,
                            crop_id,
                            unit_price,
                            unit
                        )
                    VALUES
                        (%s, %s, %s, %s);
                    """,
                    (
                        product["product_name"],
                        crop_id,
                        product["unit_price"],
                        product["unit"],
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
    generate_products()
