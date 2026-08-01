from __future__ import annotations

from pathlib import Path


def test_dag_injects_complete_batch_context_into_every_python_task() -> None:
    dag_source = Path("dags/air_quality_pipeline_dag.py").read_text(encoding="utf-8")

    assert '"PIPELINE_BATCH_ID": BATCH_ID_TEMPLATE' in dag_source
    assert '"PIPELINE_PARTITION_DATE": PARTITION_DATE_TEMPLATE' in dag_source
    assert '"PIPELINE_PARTITION_HOUR": PARTITION_HOUR_TEMPLATE' in dag_source
    assert '"PIPELINE_STARTED_AT": STARTED_AT_TEMPLATE' in dag_source


def test_dag_batch_id_is_deterministic_and_supports_manual_override() -> None:
    dag_source = Path("dags/air_quality_pipeline_dag.py").read_text(encoding="utf-8")

    assert "dag_run.conf.get('batch_id')" in dag_source
    assert "logical_date.in_timezone('UTC').strftime('%Y%m%dT%H%M%SZ')" in dag_source
    assert "~ '_airflow'" in dag_source
    assert "uuid" not in dag_source.lower()
