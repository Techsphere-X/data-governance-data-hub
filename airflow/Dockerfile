FROM apache/airflow:2.10.4

COPY --chown=airflow:root ../data-generator/requirements.txt /tmp/data-generator-requirements.txt

RUN pip install --no-cache-dir -r /tmp/data-generator-requirements.txt