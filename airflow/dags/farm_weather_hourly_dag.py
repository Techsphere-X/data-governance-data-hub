
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="farm_weather_hourly_pipeline",
    description="Generate simulated weather observations hourly",
    start_date=datetime(2026, 10, 1),
    schedule="0 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["farm", "weather", "hourly"],
) as dag:

    generate_weather = BashOperator(
        task_id="generate_weather",
        bash_command=(
            "cd /opt/airflow/data-generator && "
            "python -m src.generators.weather"
        ),
    )