from airflow.sdk import dag, task
from datetime import datetime
import requests
import os
import time
import subprocess


@dag(
    dag_id="olist_data_pipeline",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["olist", "airbyte", "dbt", "datahub"],
)
def olist_data_pipeline():

    @task
    def trigger_airbyte_sync():
        airbyte_url = os.environ["AIRBYTE_URL"]
        connection_id = os.environ["AIRBYTE_CONNECTION_ID"]
        client_id = os.environ["AIRBYTE_CLIENT_ID"]
        client_secret = os.environ["AIRBYTE_CLIENT_SECRET"]

        # --------------------------------------------------
        # 1. Get Airbyte API access token
        # --------------------------------------------------
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

        print("Airbyte API authentication successful.")

        # --------------------------------------------------
        # 2. Start the existing Olist Airbyte connection
        # --------------------------------------------------
        response = requests.post(
            f"{airbyte_url}/api/public/v1/jobs",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "jobType": "sync",
                "connectionId": connection_id,
            },
            timeout=30,
        )

        response.raise_for_status()

        job_id = response.json()["jobId"]

        print(f"Olist Airbyte sync started. Job ID: {job_id}")

        return {
            "job_id": job_id,
            "token": token,
        }

    @task
    def wait_for_airbyte(job_info):
        airbyte_url = os.environ["AIRBYTE_URL"]

        job_id = job_info["job_id"]
        token = job_info["token"]

        # --------------------------------------------------
        # 3. Wait for Airbyte job to finish
        # --------------------------------------------------
        while True:

            time.sleep(15)

            response = requests.get(
                f"{airbyte_url}/api/public/v1/jobs/{job_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                },
                timeout=30,
            )

            response.raise_for_status()

            job = response.json()
            status = job["status"]

            print(f"Olist Airbyte job {job_id} status: {status}")

            if status == "succeeded":
                print("Olist Airbyte sync completed successfully.")
                return

            if status in [
                "failed",
                "cancelled",
                "incomplete",
            ]:
                raise Exception(
                    f"Olist Airbyte sync failed. " f"Job {job_id} status: {status}"
                )

    @task
    def run_dbt_build():
        print("========================================")
        print("STARTING OLIST DBT BUILD")
        print("========================================")

        dbt_command = [
            "docker",
            "exec",
            "data-governance-dbt",
            "dbt",
            "build",
            "--select",
            "staging.* intermediate.* marts.*",
            "--exclude",
            "staging.stg_supplier_shipments "
            "intermediate.int_supplier_shipments "
            "marts.fact_supplier_shipments",
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
                f"Olist dbt build failed with exit code " f"{result.returncode}"
            )

        print("========================================")
        print("OLIST DBT BUILD COMPLETED SUCCESSFULLY")
        print("========================================")

    # ------------------------------------------------------
    # Pipeline order
    # ------------------------------------------------------
    job_info = trigger_airbyte_sync()

    airbyte_complete = wait_for_airbyte(job_info)

    airbyte_complete >> run_dbt_build()


olist_data_pipeline()
