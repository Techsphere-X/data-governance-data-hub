
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

GENERATOR_DIR = "/opt/airflow/data-generator"

with DAG(
    dag_id="farm_data_generation_pipeline",
    description="Generate farm reference and operational data",
    start_date=datetime(2026, 10, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["farm", "data-generation"],
) as dag:

    generate_farms = BashOperator(
        task_id="generate_farms",
        bash_command=f"cd {GENERATOR_DIR} && python -m src.generators.farms",
    )

    generate_fields = BashOperator(
        task_id="generate_fields",
        bash_command=f"cd {GENERATOR_DIR} && python -m src.generators.fields",
    )

    generate_crops = BashOperator(
        task_id="generate_crops",
        bash_command=f"cd {GENERATOR_DIR} && python -m src.generators.crops",
    )

    generate_products = BashOperator(
        task_id="generate_products",
        bash_command=f"cd {GENERATOR_DIR} && python -m src.generators.products",
    )

    generate_customers = BashOperator(
        task_id="generate_customers",
        bash_command=f"cd {GENERATOR_DIR} && python -m src.generators.customers",
    )

    generate_orders = BashOperator(
        task_id="generate_orders",
        bash_command=f"cd {GENERATOR_DIR} && python -m src.generators.orders",
    )

    generate_order_items = BashOperator(
        task_id="generate_order_items",
        bash_command=f"cd {GENERATOR_DIR} && python -m src.generators.order_items",
    )

    generate_harvests = BashOperator(
        task_id="generate_harvests",
        bash_command=f"cd {GENERATOR_DIR} && python -m src.generators.harvests",
    )

    generate_weather = BashOperator(
        task_id="generate_weather",
        bash_command=f"cd {GENERATOR_DIR} && python -m src.generators.weather",
    )

    generate_farms >> generate_fields
    generate_crops >> generate_products
    [generate_fields, generate_crops] >> generate_harvests
    generate_customers >> generate_orders
    [generate_orders, generate_products] >> generate_order_items