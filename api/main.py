from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg
from fastapi import (
    FastAPI,
    HTTPException,
    Query,
)
from fastapi.middleware.cors import (
    CORSMiddleware,
)
from pydantic import BaseModel

from api.database import (
    DatabaseConfigurationError,
    check_database_connection,
    get_database_settings,
)


class HealthResponse(BaseModel):
    status: str
    service: str
    database: str
    database_time: datetime


app = FastAPI(
    title=(
        "Vietnam Air Quality API"
    ),
    description=(
        "Read-only API for air quality, "
        "alerts and pipeline health data."
    ),
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ],
    allow_credentials=False,
    allow_methods=[
        "GET",
    ],
    allow_headers=[
        "*",
    ],
)


def execute_query(
    query: str,
    parameters: tuple[
        Any,
        ...,
    ] = (),
) -> list[dict[str, Any]]:
    settings = get_database_settings()

    with settings.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                parameters,
            )

            rows = cursor.fetchall()

    return list(
        rows
    )


@app.get(
    "/",
    tags=[
        "System",
    ],
)
def root() -> dict[str, str]:
    return {
        "service": (
            "Vietnam Air Quality API"
        ),
        "status": "RUNNING",
        "docs": "/docs",
        "health": "/health",
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=[
        "System",
    ],
)
def health() -> HealthResponse:
    try:
        database_result = (
            check_database_connection()
        )

    except (
        DatabaseConfigurationError,
        psycopg.Error,
        RuntimeError,
    ) as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "Không kết nối được "
                f"TimescaleDB: {error}"
            ),
        ) from error

    return HealthResponse(
        status="HEALTHY",
        service=(
            "vietnam-air-quality-api"
        ),
        database=str(
            database_result[
                "database_name"
            ]
        ),
        database_time=(
            database_result[
                "database_time"
            ]
        ),
    )


@app.get(
    "/api/v1/air-quality/latest",
    tags=[
        "Air Quality",
    ],
)
def get_latest_air_quality(
    limit: int = Query(
        default=500,
        ge=1,
        le=2000,
    ),
) -> dict[str, Any]:
    query = """
        WITH latest_batch AS (
            SELECT batch_id
            FROM fact_air_quality_hourly
            WHERE batch_id IS NOT NULL
              AND BTRIM(batch_id) <> ''
            GROUP BY batch_id
            ORDER BY
                MAX(ingested_at) DESC,
                batch_id DESC
            LIMIT 1
        )
        SELECT
            point_id,
            location_id,
            latitude,
            longitude,
            forecast_time,
            pm2_5,
            pm10,
            carbon_monoxide,
            nitrogen_dioxide,
            sulphur_dioxide,
            ozone,
            us_aqi,
            us_aqi_pm2_5,
            us_aqi_pm10,
            us_aqi_nitrogen_dioxide,
            us_aqi_carbon_monoxide,
            us_aqi_ozone,
            us_aqi_sulphur_dioxide,
            source,
            batch_id,
            schema_version,
            ingested_at
        FROM fact_air_quality_hourly
        WHERE batch_id = (
            SELECT batch_id
            FROM latest_batch
        )
        ORDER BY
            forecast_time,
            point_id
        LIMIT %s
    """

    try:
        records = execute_query(
            query=query,
            parameters=(
                limit,
            ),
        )

    except (
        DatabaseConfigurationError,
        psycopg.Error,
    ) as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Không đọc được dữ liệu "
                f"AQI mới nhất: {error}"
            ),
        ) from error

    batch_id = (
        records[0]["batch_id"]
        if records
        else None
    )

    return {
        "status": "SUCCESS",
        "batch_id": batch_id,
        "record_count": len(
            records
        ),
        "data": records,
    }


@app.get(
    "/api/v1/air-quality/points/{point_id}",
    tags=[
        "Air Quality",
    ],
)
def get_air_quality_by_point(
    point_id: str,
    limit: int = Query(
        default=24,
        ge=1,
        le=168,
    ),
) -> dict[str, Any]:
    normalized_point_id = (
        point_id.strip().upper()
    )

    if not normalized_point_id:
        raise HTTPException(
            status_code=400,
            detail="point_id không được rỗng.",
        )

    query = """
        WITH latest_batch AS (
            SELECT batch_id
            FROM fact_air_quality_hourly
            WHERE batch_id IS NOT NULL
              AND BTRIM(batch_id) <> ''
            GROUP BY batch_id
            ORDER BY
                MAX(ingested_at) DESC,
                batch_id DESC
            LIMIT 1
        )
        SELECT
            point_id,
            location_id,
            latitude,
            longitude,
            forecast_time,
            pm2_5,
            pm10,
            carbon_monoxide,
            nitrogen_dioxide,
            sulphur_dioxide,
            ozone,
            us_aqi,
            source,
            batch_id,
            ingested_at
        FROM fact_air_quality_hourly
        WHERE batch_id = (
            SELECT batch_id
            FROM latest_batch
        )
          AND point_id = %s
        ORDER BY forecast_time
        LIMIT %s
    """

    try:
        records = execute_query(
            query=query,
            parameters=(
                normalized_point_id,
                limit,
            ),
        )

    except (
        DatabaseConfigurationError,
        psycopg.Error,
    ) as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Không đọc được dữ liệu "
                f"của monitoring point: {error}"
            ),
        ) from error

    if not records:
        raise HTTPException(
            status_code=404,
            detail=(
                "Không tìm thấy dữ liệu "
                f"cho point_id "
                f"{normalized_point_id}."
            ),
        )

    return {
        "status": "SUCCESS",
        "point_id": (
            normalized_point_id
        ),
        "batch_id": (
            records[0]["batch_id"]
        ),
        "record_count": len(
            records
        ),
        "data": records,
    }


@app.get(
    "/api/v1/alerts/latest",
    tags=[
        "Alerts",
    ],
)
def get_latest_alerts(
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
    ),
) -> dict[str, Any]:
    query = """
        SELECT *
        FROM fact_air_quality_alerts
        ORDER BY
            created_at DESC
        LIMIT %s
    """

    try:
        records = execute_query(
            query=query,
            parameters=(
                limit,
            ),
        )

    except (
        DatabaseConfigurationError,
        psycopg.Error,
    ) as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Không đọc được dữ liệu "
                f"alert: {error}"
            ),
        ) from error

    return {
        "status": "SUCCESS",
        "record_count": len(
            records
        ),
        "data": records,
    }


@app.get(
    "/api/v1/pipeline/health/latest",
    tags=[
        "Pipeline Health",
    ],
)
def get_latest_pipeline_health() -> dict[
    str,
    Any,
]:
    query = """
        WITH latest_batch AS (
            SELECT batch_id
            FROM pipeline_run_logs
            WHERE batch_id IS NOT NULL
              AND BTRIM(batch_id) <> ''
            ORDER BY updated_at DESC
            LIMIT 1
        )
        SELECT
            run_id,
            batch_id,
            pipeline_name,
            source,
            stage_name,
            status,
            started_at,
            finished_at,
            duration_seconds,
            input_records,
            output_records,
            failed_records,
            error_message,
            summary_bucket,
            summary_object_name,
            updated_at
        FROM pipeline_run_logs
        WHERE batch_id = (
            SELECT batch_id
            FROM latest_batch
        )
        ORDER BY
            CASE stage_name
                WHEN 'extract' THEN 1
                WHEN 'transform' THEN 2
                WHEN 'data_quality' THEN 3
                WHEN 'load_timescaledb' THEN 4
                WHEN 'alerts' THEN 5
                ELSE 10
            END
    """

    try:
        records = execute_query(
            query=query
        )

    except (
        DatabaseConfigurationError,
        psycopg.Error,
    ) as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Không đọc được Pipeline "
                f"Health: {error}"
            ),
        ) from error

    if not records:
        return {
            "status": "EMPTY",
            "batch_id": None,
            "stage_count": 0,
            "data": [],
        }

    pipeline_status = (
        "SUCCESS"
        if all(
            record["status"]
            == "SUCCESS"
            for record in records
        )
        else "FAILED"
    )

    return {
        "status": pipeline_status,
        "batch_id": (
            records[0]["batch_id"]
        ),
        "stage_count": len(
            records
        ),
        "data": records,
    }


@app.get(
    "/api/v1/data-quality/latest",
    tags=[
        "Pipeline Health",
    ],
)
def get_latest_data_quality() -> dict[
    str,
    Any,
]:
    query = """
        WITH latest_batch AS (
            SELECT batch_id
            FROM data_quality_logs
            WHERE batch_id IS NOT NULL
              AND BTRIM(batch_id) <> ''
            ORDER BY updated_at DESC
            LIMIT 1
        )
        SELECT
            run_id,
            batch_id,
            check_name,
            status,
            bad_records_count,
            message,
            checked_at,
            summary_bucket,
            summary_object_name,
            updated_at
        FROM data_quality_logs
        WHERE batch_id = (
            SELECT batch_id
            FROM latest_batch
        )
        ORDER BY check_name
    """

    try:
        records = execute_query(
            query=query
        )

    except (
        DatabaseConfigurationError,
        psycopg.Error,
    ) as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Không đọc được Data "
                f"Quality logs: {error}"
            ),
        ) from error

    failed_checks = [
        record
        for record in records
        if record["status"]
        not in {
            "PASSED",
            "SUCCESS",
        }
    ]

    return {
        "status": (
            "PASSED"
            if not failed_checks
            else "FAILED"
        ),
        "check_count": len(
            records
        ),
        "failed_check_count": len(
            failed_checks
        ),
        "data": records,
    }