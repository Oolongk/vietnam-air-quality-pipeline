FROM apache/airflow:2.11.2-python3.11

COPY requirements.txt /opt/airflow/requirements-project.txt

# Keep the Airflow version from the base image pinned while pip resolves
# the project dependencies. This prevents an accidental Airflow upgrade
# or downgrade caused by another package.
RUN pip install \
        --no-cache-dir \
        "apache-airflow==2.11.2" \
        -r /opt/airflow/requirements-project.txt \
    && pip check
