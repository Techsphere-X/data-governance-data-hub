import psycopg2

from src.config import (
    DB_HOST,
    DB_PORT,
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
    DB_SCHEMA,
)


def get_connection():
    connection = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )

    return connection


def test_connection():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_schema();")
            database, schema = cursor.fetchone()

            print(f"Connected to database: {database}")
            print(f"Current schema: {schema}")

            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                ORDER BY table_name;
                """,
                (DB_SCHEMA,),
            )

            tables = cursor.fetchall()

            print(f"\nTables in {DB_SCHEMA}:")

            for table in tables:
                print(f"  - {table[0]}")

    finally:
        connection.close()


if __name__ == "__main__":
    test_connection()