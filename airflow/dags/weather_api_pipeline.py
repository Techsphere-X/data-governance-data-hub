from airflow.sdk import dag, task
from datetime import datetime
import requests
import os
import time
import subprocess


@dag(
    dag_id="weather_api_pipeline",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["weather", "noaa", "airbyte", "dbt"],
)
def weather_api_pipeline():

    @task
    def trigger_weather_airbyte_sync():
        airbyte_url = os.environ["AIRBYTE_URL"]
        connection_id = os.environ["WEATHER_AIRBYTE_CONNECTION_ID"]
        client_id = os.environ["AIRBYTE_CLIENT_ID"]
        client_secret = os.environ["AIRBYTE_CLIENT_SECRET"]

        # 1. Authenticate with Airbyte
        token_response = requests.post(
            f"{airbyte_url}/api/public/v1/applications/token",
            json={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant-type": "client_credentials",
            },
            timeout=30,
        )

        token_response.raise_for_status()
        token = token_response.json()["access_token"]

        print("Weather Airbyte API authentication successful.")

        # 2. Start the existing weather connection
        response = requests.post(
            f"{airbyte_url}/api/public/v1/jobs",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "jobType": "sync",
                "connectionId": connection_id,
            },
            timeout=30,
        )

        response.raise_for_status()
        job_id = response.json()["jobId"]

        print(f"Weather Airbyte sync started. Job ID: {job_id}")

        return job_id

    @task
    def wait_for_weather_airbyte(job_id):
        airbyte_url = os.environ["AIRBYTE_URL"]
        client_id = os.environ["AIRBYTE_CLIENT_ID"]
        client_secret = os.environ["AIRBYTE_CLIENT_SECRET"]

        # 3. Poll Airbyte until the sync finishes
        while True:
            time.sleep(15)

            # Refresh the access token while polling
            token_response = requests.post(
                f"{airbyte_url}/api/public/v1/applications/token",
                json={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant-type": "client_credentials",
                },
                timeout=30,
            )

            token_response.raise_for_status()
            token = token_response.json()["access_token"]

            status_response = requests.get(
                f"{airbyte_url}/api/public/v1/jobs/{job_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )

            status_response.raise_for_status()
            job = status_response.json()
            status = job["status"]

            print(f"Weather Airbyte job {job_id} status: {status}")

            if status == "succeeded":
                print("Weather Airbyte sync completed successfully.")
                return

            if status in ["failed", "cancelled", "incomplete"]:
                raise Exception(
                    f"Weather Airbyte sync failed. " f"Job {job_id} status: {status}"
                )

    @task
    def run_weather_dbt_build():
        print("========================================")
        print("STARTING WEATHER DBT BUILD AND TESTS")
        print("========================================")

        dbt_command = [
            "docker",
            "exec",
            "data-governance-dbt",
            "dbt",
            "build",
            "--select",
            "stg_weather_sao",
            "stg_weather_rio",
        ]

        print(f"Running command: {' '.join(dbt_command)}")

        result = subprocess.run(
            dbt_command,
            capture_output=True,
            text=True,
        )

        print("========================================")
        print("DBT OUTPUT")
        print("========================================")
        print(result.stdout)

        if result.stderr:
            print("========================================")
            print("DBT STDERR")
            print("========================================")
            print(result.stderr)

        print("========================================")
        print(f"DBT RETURN CODE: {result.returncode}")
        print("========================================")

        if result.returncode != 0:
            raise Exception(
                f"Weather dbt build or tests failed with exit code "
                f"{result.returncode}"
            )

        print("Weather dbt build and tests completed successfully.")

    # Pipeline order:
    # Airbyte sync -> wait for completion -> dbt build and tests
    job_id = trigger_weather_airbyte_sync()
    airbyte_complete = wait_for_weather_airbyte(job_id)
    airbyte_complete >> run_weather_dbt_build()


weather_api_pipeline()
