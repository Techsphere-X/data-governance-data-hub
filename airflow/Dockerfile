FROM apache/airflow:2.10.4

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
USER airflow

COPY --chown=airflow:root ../data-generator/requirements.txt /tmp/data-generator-requirements.txt

RUN pip install --no-cache-dir -r /tmp/data-generator-requirements.txt

# Install dbt in an isolated virtual environment.
RUN python -m venv /home/airflow/dbt-venv \
    && /home/airflow/dbt-venv/bin/pip install --no-cache-dir \
       dbt-core==1.12.3 \
       dbt-postgres==1.11.0