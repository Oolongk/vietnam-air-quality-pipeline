from __future__ import annotations

from datetime import timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
import pendulum

from src.operations.airflow_callbacks import (
    notify_dag_failure,
    notify_task_failure,
    notify_task_retry,
)

DAG_ID = "vietnam_air_quality_minio_pipeline"
PROJECT_ROOT = "/opt/airflow/project"
LOCAL_TIMEZONE = pendulum.timezone("Asia/Ho_Chi_Minh")

DAG_RUN_TIMEOUT = timedelta(minutes=80)
DEFAULT_EXECUTION_TIMEOUT = timedelta(minutes=10)


def build_python_command(
    module_name: str,
) -> str:
    """Build a fail-fast command for a project Python module."""

    return (
        "set -euo pipefail\n"
        f"cd {PROJECT_ROOT}\n"
        f'echo "[airflow] Starting module: '
        f'{module_name}"\n'
        f"exec python -m {module_name}"
    )


def create_python_task(
    *,
    task_id: str,
    module_name: str,
    execution_timeout: timedelta = (DEFAULT_EXECUTION_TIMEOUT),
) -> BashOperator:
    """Create a consistently configured Python-module task."""

    return BashOperator(
        task_id=task_id,
        bash_command=build_python_command(module_name),
        execution_timeout=execution_timeout,
        append_env=True,
        env={
            "PYTHONUNBUFFERED": "1",
        },
        do_xcom_push=False,
    )


default_args = {
    "owner": "air-quality-team",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=3),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=15),
    "on_failure_callback": notify_task_failure,
    "on_retry_callback": notify_task_retry,
}


with DAG(
    dag_id=DAG_ID,
    description=(
        "Open-Meteo Air Quality pipeline using MinIO, TimescaleDB and Airflow"
    ),
    default_args=default_args,
    start_date=pendulum.datetime(
        2026,
        7,
        14,
        tz=LOCAL_TIMEZONE,
    ),
    schedule="*/30 * * * *",
    catchup=False,
    max_active_runs=1,
    max_active_tasks=2,
    dagrun_timeout=DAG_RUN_TIMEOUT,
    on_failure_callback=notify_dag_failure,
    tags=[
        "air-quality",
        "open-meteo",
        "minio",
        "timescaledb",
        "mart",
        "snapshot",
        "s3",
    ],
    doc_md="""
    ## Vietnam Air Quality MinIO Pipeline

    Pipeline chạy mỗi 30 phút.

    - Mỗi task có execution timeout riêng.
    - Task lỗi được retry tối đa 2 lần với exponential backoff.
    - Chỉ một DAG run được hoạt động tại một thời điểm.
    - Task failure và DAG failure được lưu thành JSON Lines.
    - Webhook chỉ được gọi khi `AIRFLOW_ALERT_WEBHOOK_URL`
      được cấu hình.
    """,
) as dag:
    sync_dimensions = create_python_task(
        task_id="sync_dimensions",
        module_name=("scripts.sync_dimensions_to_timescaledb"),
        execution_timeout=timedelta(minutes=5),
    )

    extract_to_minio = create_python_task(
        task_id="extract_to_minio",
        module_name=("scripts.extract_all_points_to_minio"),
        execution_timeout=timedelta(minutes=12),
    )

    transform_minio_batch = create_python_task(
        task_id="transform_minio_batch",
        module_name=("scripts.transform_latest_minio_batch"),
        execution_timeout=timedelta(minutes=8),
    )

    run_data_quality = create_python_task(
        task_id="run_data_quality",
        module_name=("scripts.run_latest_minio_data_quality"),
        execution_timeout=timedelta(minutes=8),
    )

    load_timescaledb = create_python_task(
        task_id="load_timescaledb",
        module_name=("scripts.load_latest_minio_clean_batch"),
        execution_timeout=timedelta(minutes=10),
    )

    process_aqi_alerts = create_python_task(
        task_id="process_aqi_alerts",
        module_name=("scripts.process_latest_aqi_alerts"),
        execution_timeout=timedelta(minutes=8),
    )

    build_minio_mart = create_python_task(
        task_id="build_minio_mart",
        module_name=("scripts.build_latest_minio_mart"),
        execution_timeout=timedelta(minutes=10),
    )

    sync_pipeline_health = create_python_task(
        task_id="sync_pipeline_health",
        module_name=("scripts.sync_latest_minio_pipeline_health"),
        execution_timeout=timedelta(minutes=6),
    )

    publish_public_snapshots = create_python_task(
        task_id=("publish_public_snapshots"),
        module_name=("scripts.publish_latest_snapshots"),
        execution_timeout=timedelta(minutes=12),
    )

    upload_public_snapshots_to_s3 = create_python_task(
        task_id=("upload_public_snapshots_to_s3"),
        module_name=("scripts.upload_public_snapshots_to_s3"),
        execution_timeout=timedelta(minutes=12),
    )

    (sync_dimensions >> extract_to_minio >> transform_minio_batch >> run_data_quality)

    (run_data_quality >> load_timescaledb >> process_aqi_alerts)

    run_data_quality >> build_minio_mart

    [
        process_aqi_alerts,
        build_minio_mart,
    ] >> sync_pipeline_health

    (sync_pipeline_health >> publish_public_snapshots >> upload_public_snapshots_to_s3)
