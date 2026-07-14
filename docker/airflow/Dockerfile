FROM apache/airflow:2.11.2-python3.11

COPY requirements.txt /opt/airflow/requirements-project.txt

RUN pip install \
    --no-cache-dir \
    -r /opt/airflow/requirements-project.txt