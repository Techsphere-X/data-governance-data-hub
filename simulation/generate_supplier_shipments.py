import csv
import os
import random
from datetime import date, datetime, timedelta

import boto3
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# PostgreSQL connection settings for supplier shipment generation
SUPPLIER_DB_HOST = os.getenv("SUPPLIER_DB_HOST", "localhost")
SUPPLIER_DB_PORT = os.getenv("SUPPLIER_DB_PORT", "5432")
SUPPLIER_DB_NAME = os.getenv("SUPPLIER_DB_NAME", "governance")
SUPPLIER_DB_USER = os.getenv("SUPPLIER_DB_USER", "governance")
SUPPLIER_DB_PASSWORD = os.getenv("SUPPLIER_DB_PASSWORD")

# MinIO settings
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9100")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "supplieradmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "supplieradmin123")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "supplier-data")
MINIO_PREFIX = "shipments/"

# How many shipment records to generate
NUMBER_OF_SHIPMENTS = 20

# Where to save the generated CSV
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "incoming",
)


def get_product_ids():
    """Get real product IDs from PostgreSQL."""

    connection = psycopg2.connect(
        host=SUPPLIER_DB_HOST,
        port=SUPPLIER_DB_PORT,
        database=SUPPLIER_DB_NAME,
        user=SUPPLIER_DB_USER,
        password=SUPPLIER_DB_PASSWORD,
    )

    cursor = connection.cursor()

    cursor.execute("""
        SELECT product_id
        FROM public.olist_products
        WHERE product_id IS NOT NULL;
    """)

    product_ids = [row[0] for row in cursor.fetchall()]

    cursor.close()
    connection.close()

    return product_ids


def generate_shipments(product_ids):
    """Generate simulated supplier shipment records."""

    shipments = []

    suppliers = [
        "SUP001",
        "SUP002",
        "SUP003",
        "SUP004",
        "SUP005",
    ]

    statuses = [
        "Pending",
        "In Transit",
        "Delivered",
        "Delayed",
    ]

    today = date.today()

    for number in range(1, NUMBER_OF_SHIPMENTS + 1):

        shipment_date = today - timedelta(
            days=random.randint(0, 7)
        )

        expected_delivery_date = shipment_date + timedelta(
            days=random.randint(3, 7)
        )

        status = random.choice(statuses)

        # Delivered and delayed shipments have an actual delivery date.
        if status in ["Delivered", "Delayed"]:
            actual_delivery_date = expected_delivery_date + timedelta(
                days=random.randint(-2, 3)
            )
        else:
            actual_delivery_date = None

        shipment = {
            "shipment_id": (
                f"SHP{datetime.now().strftime('%Y%m%d%H%M%S')}"
                f"{number:03d}"
            ),
            "product_id": random.choice(product_ids),
            "supplier_id": random.choice(suppliers),
            "shipment_date": shipment_date,
            "quantity": random.randint(1, 50),
            "expected_delivery_date": expected_delivery_date,
            "actual_delivery_date": actual_delivery_date,
            "shipment_status": status,
            "updated_at": datetime.now(),
        }

        shipments.append(shipment)

    return shipments


def save_to_csv(shipments):
    """Save shipments to a new CSV file."""

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    filename = f"shipments_{timestamp}.csv"

    filepath = os.path.join(OUTPUT_DIR, filename)

    fieldnames = [
        "shipment_id",
        "product_id",
        "supplier_id",
        "shipment_date",
        "quantity",
        "expected_delivery_date",
        "actual_delivery_date",
        "shipment_status",
        "updated_at",
    ]

    with open(
        filepath,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(shipments)

    return filepath


def upload_to_minio(filepath):
    """Upload the generated CSV to MinIO."""

    s3 = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        region_name="us-east-1",
    )

    filename = os.path.basename(filepath)

    object_key = f"{MINIO_PREFIX}{filename}"

    s3.upload_file(
        filepath,
        MINIO_BUCKET,
        object_key,
    )

    print(
        f"Uploaded to MinIO: "
        f"{MINIO_BUCKET}/{object_key}"
    )


def main():
    print("Connecting to PostgreSQL...")

    if not SUPPLIER_DB_PASSWORD:
        raise ValueError(
            "DB_PASSWORD is not set. "
            "Set it before running the script."
        )

    product_ids = get_product_ids()

    if not product_ids:
        raise ValueError(
            "No product IDs were found in "
            "public.olist_products."
        )

    print(
        f"Found {len(product_ids)} existing product IDs."
    )

    shipments = generate_shipments(product_ids)

    filepath = save_to_csv(shipments)

    print(
        f"Generated {len(shipments)} shipment records."
    )

    print(f"CSV created: {filepath}")

    # Upload the generated CSV to MinIO
    upload_to_minio(filepath)


if __name__ == "__main__":
    main()