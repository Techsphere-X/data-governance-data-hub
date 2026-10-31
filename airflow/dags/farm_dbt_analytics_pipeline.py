from datetime import datetime, timedelta
import logging
import os
import time
from pathlib import Path

import requests

from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator


# --------------------------------------------------
# Configuration
# --------------------------------------------------

AIRBYTE_CONNECTION_ID = "0a282138-cd86-49ee-8a87-aa8320ddfd44"
AIRBYTE_POLL_INTERVAL = 15
AIRBYTE_TIMEOUT_SECONDS = 1800  # 30 minutes

DBT_PROJECT_DIR = "/opt/airflow/dbt"
DBT_EXECUTABLE = "/home/airflow/dbt-venv/bin/dbt"
DBT_PROFILES_DIR = "/tmp/airflow-dbt-profiles"
DBT_PROFILE_FILE = f"{DBT_PROFILES_DIR}/profiles.yml"


# --------------------------------------------------
# Airbyte API helpers
# --------------------------------------------------

def airbyte_api_request(method, path, payload=None):
    """Call the Airbyte public API using a fresh access token."""

    api_url = os.environ.get("AIRBYTE_API_URL")
    client_id = os.environ.get("AIRBYTE_CLIENT_ID")
    client_secret = os.environ.get("AIRBYTE_CLIENT_SECRET")

    missing = [
        name
        for name, value in (
            ("AIRBYTE_API_URL", api_url),
            ("AIRBYTE_CLIENT_ID", client_id),
            ("AIRBYTE_CLIENT_SECRET", client_secret),
        )
        if not value
    ]

    if missing:
        raise AirflowException(
            f"Missing Airbyte environment variables: {missing}"
        )

    # Accept either a host URL or a URL containing an API path.
    base_url = api_url.split("/api/")[0].rstrip("/")
    public_api_url = f"{base_url}/api/public/v1"

    token_response = requests.post(
        f"{public_api_url}/applications/token",
        json={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant-type": "client_credentials",
        },
        timeout=20,
    )
    token_response.raise_for_status()

    token = token_response.json().get("access_token")
    if not token:
        raise AirflowException("Airbyte authentication returned no access token.")

    response = requests.request(
        method=method,
        url=f"{public_api_url}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()

    if not response.content:
        return {}

    return response.json()


def trigger_airbyte_sync():
    """Start the farm PostgreSQL to Postgres sync."""

    job = airbyte_api_request(
        "POST",
        "/jobs",
        payload={
            "jobType": "sync",
            "connectionId": AIRBYTE_CONNECTION_ID,
        },
    )

    job_id = job.get("jobId")
    if job_id is None:
        raise AirflowException(
            f"Airbyte did not return a job ID. Response: {job}"
        )

    logging.info(
        "Started Airbyte sync. Job ID=%s, initial status=%s",
        job_id,
        job.get("status"),
    )

    # Airflow passes this value to the waiting task using XCom.
    return job_id


def wait_for_airbyte_sync(ti):
    """Wait for the Airbyte job to succeed or fail."""

    job_id = ti.xcom_pull(task_ids="trigger_airbyte_sync")

    if job_id is None:
        raise AirflowException("Could not retrieve the Airbyte job ID from XCom.")

    deadline = time.monotonic() + AIRBYTE_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        job = airbyte_api_request("GET", f"/jobs/{job_id}")
        status = str(job.get("status", "")).lower()

        logging.info(
            "Airbyte job %s status=%s, rowsSynced=%s, bytesSynced=%s",
            job_id,
            status,
            job.get("rowsSynced"),
            job.get("bytesSynced"),
        )

        if status == "succeeded":
            logging.info(
                "Airbyte sync succeeded. Job ID=%s, rowsSynced=%s, "
                "bytesSynced=%s",
                job_id,
                job.get("rowsSynced", 0),
                job.get("bytesSynced", 0),
            )
            return

        if status in {"failed", "cancelled"}:
            raise AirflowException(
                f"Airbyte job {job_id} ended with status '{status}'."
            )

        # Pending, running, and intermediate states are polled again.
        time.sleep(AIRBYTE_POLL_INTERVAL)

    raise AirflowException(
        f"Airbyte job {job_id} did not succeed within "
        f"{AIRBYTE_TIMEOUT_SECONDS} seconds."
    )


# --------------------------------------------------
# dbt profile
# --------------------------------------------------

def create_dbt_profile():
    """Create an Airflow-specific dbt profile."""

    Path(DBT_PROFILES_DIR).mkdir(parents=True, exist_ok=True)

    required_vars = [
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
    ]
    missing = [name for name in required_vars if not os.environ.get(name)]

    if missing:
        raise AirflowException(
            f"Missing database environment variables: {missing}"
        )

    profile = f"""data_governance:
  target: dev
  outputs:
    dev:
      type: postgres
      host: {os.environ["DB_HOST"]}
      port: {os.environ["DB_PORT"]}
      user: {os.environ["DB_USER"]}
      password: '{os.environ["DB_PASSWORD"]}'
      dbname: {os.environ["DB_NAME"]}
      schema: analytics
      threads: 4
"""

    Path(DBT_PROFILE_FILE).write_text(profile, encoding="utf-8")


# --------------------------------------------------
# DAG
# --------------------------------------------------

default_args = {
    "owner": "data-platform",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="farm_dbt_analytics_pipeline",
    description="Sync farm data with Airbyte, build and test dbt Silver and Gold models",
    default_args=default_args,
    start_date=datetime(2026, 10, 14),
    schedule="@daily",
    catchup=False,
    tags=["farm", "airbyte", "dbt", "analytics"],
) as dag:

    trigger_sync = PythonOperator(
        task_id="trigger_airbyte_sync",
        python_callable=trigger_airbyte_sync,
        # Avoid creating a second sync if the trigger task is retried
        # after an ambiguous network response.
        retries=0,
    )

    wait_for_sync = PythonOperator(
        task_id="wait_for_airbyte_sync",
        python_callable=wait_for_airbyte_sync,
    )

    prepare_dbt_profile = PythonOperator(
        task_id="prepare_dbt_profile",
        python_callable=create_dbt_profile,
    )

    run_silver_gold = BashOperator(
        task_id="run_silver_gold_models",
        bash_command=(
            f"export DBT_LOG_PATH=/tmp/dbt-logs && "
            f"{DBT_EXECUTABLE} run "
            f"--project-dir {DBT_PROJECT_DIR} "
            f"--target-path /tmp/airflow-dbt-target "
            f"--profiles-dir {DBT_PROFILES_DIR} "
            f"--select path:models/silver path:models/gold"
        ),
    )

    test_silver_gold = BashOperator(
        task_id="test_silver_gold_models",
        bash_command=(
            f"export DBT_LOG_PATH=/tmp/dbt-logs && "
            f"{DBT_EXECUTABLE} test "
            f"--project-dir {DBT_PROJECT_DIR} "
            f"--target-path /tmp/airflow-dbt-target "
            f"--profiles-dir {DBT_PROFILES_DIR} "
            f"--select path:models/silver path:models/gold"
        ),
    )

    (
        trigger_sync
        >> wait_for_sync
        >> prepare_dbt_profile
        >> run_silver_gold
        >> test_silver_gold
    )