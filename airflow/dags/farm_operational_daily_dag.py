
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


GENERATOR_DIR = "/opt/airflow/data-generator"

with DAG(
    dag_id="farm_operational_daily_pipeline",
    description="Generate daily farm operational data",
    start_date=datetime(2026, 10, 1),
    schedule="0 1 * * *",  
    catchup=False,
    max_active_runs=1,
    tags=["farm", "daily", "data-generation"],
) as dag:

    generate_customers = BashOperator(
        task_id="generate_customers",
        bash_command=(
            f"cd {GENERATOR_DIR} && "
            "python -m src.generators.customers"
        ),
    )

    generate_orders = BashOperator(
        task_id="generate_orders",
        bash_command=(
            f"cd {GENERATOR_DIR} && "
            "python -m src.generators.orders"
        ),
    )

    generate_order_items = BashOperator(
        task_id="generate_order_items",
        bash_command=(
            f"cd {GENERATOR_DIR} && "
            "python -m src.generators.order_items"
        ),
    )

    generate_harvests = BashOperator(
        task_id="generate_harvests",
        bash_command=(
            f"cd {GENERATOR_DIR} && "
            "python -m src.generators.harvests"
        ),
    )

    generate_customers >> generate_orders >> generate_order_items