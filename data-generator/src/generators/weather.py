
import random
from datetime import datetime
from decimal import Decimal

from src.database import get_connection


LOCATIONS = [
    "Kathmandu Valley",
    "Chitwan",
    "Pokhara",
]


def generate_weather():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            for location in LOCATIONS:
                temperature_c = Decimal(
                    str(round(random.uniform(10, 35), 2))
                )
                humidity_percent = Decimal(
                    str(round(random.uniform(40, 95), 2))
                )
                precipitation_mm = Decimal(
                    str(round(random.uniform(0, 30), 2))
                )
                wind_speed_kmh = Decimal(
                    str(round(random.uniform(0, 40), 2))
                )

                cursor.execute(
                    """
                    INSERT INTO farm_source.weather (
                        recorded_at,
                        location,
                        temperature_c,
                        humidity_percent,
                        precipitation_mm,
                        wind_speed_kmh
                    )
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (
                        datetime.now(),
                        location,
                        temperature_c,
                        humidity_percent,
                        precipitation_mm,
                        wind_speed_kmh,
                    ),
                )

        connection.commit()
        print(
            f"Inserted {len(LOCATIONS)} weather records "
            f"for {datetime.now():%Y-%m-%d %H:%M:%S}."
        )

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    generate_weather()