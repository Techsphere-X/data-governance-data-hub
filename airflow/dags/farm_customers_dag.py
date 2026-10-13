
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="farm_customers_pipeline",
    description="Generate farm customer data in PostgreSQL",
    start_date=datetime(2026, 10, 1),
    schedule=None,
    catchup=False,
    tags=["farm", "generator"],
) as dag:

    generate_customers = BashOperator(
        task_id="generate_customers",
        bash_command=(
            "cd /opt/airflow/data-generator && "
            "python -m src.generators.customers"
        ),
    )