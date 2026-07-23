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
    "/api/v1/locations",
    tags=[
        "Dimensions",
    ],
)
def get_locations() -> dict[str, Any]:
    query = """
        SELECT
            location_id,
            location_name,
            region,
            admin_type,
            is_active,
            created_at,
            updated_at
        FROM dim_location
        WHERE is_active IS TRUE
        ORDER BY
            region,
            location_name
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
                "Không đọc được danh sách "
                f"tỉnh/thành: {error}"
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
    "/api/v1/monitoring-points",
    tags=[
        "Dimensions",
    ],
)
def get_monitoring_points() -> dict[
    str,
    Any,
]:
    query = """
        SELECT
            p.point_id,
            p.location_id,
            p.point_name,
            p.point_type,
            p.latitude,
            p.longitude,
            p.is_active,
            p.created_at,
            p.updated_at,

            l.location_name,
            l.region,
            l.admin_type

        FROM dim_monitoring_point AS p

        INNER JOIN dim_location AS l
            ON l.location_id = p.location_id

        WHERE p.is_active IS TRUE
          AND l.is_active IS TRUE

        ORDER BY
            l.location_name,
            p.point_name
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
                "Không đọc được danh sách "
                f"monitoring point: {error}"
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
    "/api/v1/air-quality/locations/{location_id}",
    tags=[
        "Air Quality",
    ],
)
def get_air_quality_by_location(
    location_id: str,
    limit: int = Query(
        default=72,
        ge=1,
        le=2000,
    ),
) -> dict[str, Any]:
    normalized_location_id = (
        location_id.strip().upper()
    )

    if not normalized_location_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "location_id không được rỗng."
            ),
        )

    query = """
        WITH latest_batch AS (
            SELECT
                batch_id
            FROM fact_air_quality_hourly
            ORDER BY
                ingested_at DESC,
                batch_id DESC
            LIMIT 1
        )
        SELECT
            f.point_id,
            f.location_id,

            p.point_name,
            p.point_type,

            l.location_name,
            l.region,
            l.admin_type,

            p.latitude,
            p.longitude,

            f.forecast_time,
            f.pm2_5,
            f.pm10,
            f.carbon_monoxide,
            f.nitrogen_dioxide,
            f.sulphur_dioxide,
            f.ozone,
            f.us_aqi,
            f.us_aqi_pm2_5,
            f.us_aqi_pm10,
            f.us_aqi_nitrogen_dioxide,
            f.us_aqi_carbon_monoxide,
            f.us_aqi_ozone,
            f.us_aqi_sulphur_dioxide,
            f.aqi_level,
            f.aqi_severity,
            f.source,
            f.batch_id,
            f.schema_version,
            f.ingested_at

        FROM fact_air_quality_hourly AS f

        INNER JOIN dim_monitoring_point AS p
            ON p.point_id = f.point_id

        INNER JOIN dim_location AS l
            ON l.location_id = f.location_id

        WHERE f.batch_id = (
            SELECT batch_id
            FROM latest_batch
        )
          AND f.location_id = %s

        ORDER BY
            f.forecast_time,
            f.point_id

        LIMIT %s
    """

    try:
        records = execute_query(
            query=query,
            parameters=(
                normalized_location_id,
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
                "AQI của tỉnh/thành: "
                f"{error}"
            ),
        ) from error

    if not records:
        raise HTTPException(
            status_code=404,
            detail=(
                "Không tìm thấy dữ liệu "
                "cho location_id "
                f"{normalized_location_id}."
            ),
        )

    return {
        "status": "SUCCESS",
        "location_id": (
            normalized_location_id
        ),
        "location_name": (
            records[0]["location_name"]
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
            SELECT
                batch_id
            FROM fact_air_quality_hourly
            ORDER BY
                ingested_at DESC,
                batch_id DESC
            LIMIT 1
        )
        SELECT
            f.point_id,
            f.location_id,

            p.point_name,
            p.point_type,

            l.location_name,
            l.region,
            l.admin_type,

            p.latitude,
            p.longitude,

            f.forecast_time,
            f.pm2_5,
            f.pm10,
            f.carbon_monoxide,
            f.nitrogen_dioxide,
            f.sulphur_dioxide,
            f.ozone,
            f.us_aqi,
            f.us_aqi_pm2_5,
            f.us_aqi_pm10,
            f.us_aqi_nitrogen_dioxide,
            f.us_aqi_carbon_monoxide,
            f.us_aqi_ozone,
            f.us_aqi_sulphur_dioxide,
            f.source,
            f.batch_id,
            f.schema_version,
            f.ingested_at

        FROM fact_air_quality_hourly AS f

        INNER JOIN dim_monitoring_point AS p
            ON p.point_id = f.point_id

        INNER JOIN dim_location AS l
            ON l.location_id = f.location_id

        WHERE f.batch_id = (
            SELECT batch_id
            FROM latest_batch
        )

        ORDER BY
            f.forecast_time,
            f.point_id

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
    "/api/v1/air-quality/top-polluted",
    tags=[
        "Air Quality",
    ],
)
def get_top_polluted(
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
    ),
) -> dict[str, Any]:
    query = """
        WITH latest_batch AS (
            SELECT
                batch_id
            FROM fact_air_quality_hourly
            ORDER BY
                ingested_at DESC,
                batch_id DESC
            LIMIT 1
        ),
        reference_time AS (
            SELECT
                MIN(forecast_time)
                    AS forecast_time
            FROM fact_air_quality_hourly
            WHERE batch_id = (
                SELECT batch_id
                FROM latest_batch
            )
        )
        SELECT
            f.point_id,
            f.location_id,

            p.point_name,
            p.point_type,

            l.location_name,
            l.region,
            l.admin_type,

            p.latitude,
            p.longitude,

            f.forecast_time,
            f.pm2_5,
            f.pm10,
            f.carbon_monoxide,
            f.nitrogen_dioxide,
            f.sulphur_dioxide,
            f.ozone,
            f.us_aqi,
            f.aqi_level,
            f.aqi_severity,
            f.source,
            f.batch_id,
            f.ingested_at

        FROM fact_air_quality_hourly AS f

        INNER JOIN dim_monitoring_point AS p
            ON p.point_id = f.point_id

        INNER JOIN dim_location AS l
            ON l.location_id = f.location_id

        WHERE f.batch_id = (
            SELECT batch_id
            FROM latest_batch
        )
          AND f.forecast_time = (
              SELECT forecast_time
              FROM reference_time
          )
          AND f.us_aqi IS NOT NULL

        ORDER BY
            f.us_aqi DESC,
            l.location_name,
            p.point_name

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
                "Không đọc được danh sách "
                "monitoring point ô nhiễm nhất: "
                f"{error}"
            ),
        ) from error

    batch_id = (
        records[0]["batch_id"]
        if records
        else None
    )

    reference_time = (
        records[0]["forecast_time"]
        if records
        else None
    )

    return {
        "status": "SUCCESS",
        "batch_id": batch_id,
        "reference_time": reference_time,
        "record_count": len(
            records
        ),
        "data": records,
    }

@app.get(
    "/api/v1/air-quality/history",
    tags=[
        "Air Quality",
    ],
)
def get_air_quality_history(
    point_id: str = Query(
        ...,
        min_length=1,
    ),
    hours: int = Query(
        default=168,
        ge=1,
        le=2160,
    ),
) -> dict[str, Any]:
    normalized_point_id = (
        point_id.strip().upper()
    )

    if not normalized_point_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "point_id không được rỗng."
            ),
        )

    query = """
        WITH recent_history AS (
            SELECT
                f.point_id,
                f.location_id,
                f.forecast_time,
                f.pm2_5,
                f.pm10,
                f.carbon_monoxide,
                f.nitrogen_dioxide,
                f.sulphur_dioxide,
                f.ozone,
                f.us_aqi,
                f.us_aqi_pm2_5,
                f.us_aqi_pm10,
                f.us_aqi_nitrogen_dioxide,
                f.us_aqi_carbon_monoxide,
                f.us_aqi_ozone,
                f.us_aqi_sulphur_dioxide,
                f.aqi_level,
                f.aqi_severity,
                f.source,
                f.batch_id,
                f.schema_version,
                f.ingested_at

            FROM fact_air_quality_hourly AS f

            WHERE f.point_id = %s

            ORDER BY
                f.forecast_time DESC

            LIMIT %s
        )
        SELECT
            history.point_id,
            history.location_id,

            point.point_name,
            point.point_type,

            location.location_name,
            location.region,
            location.admin_type,

            point.latitude,
            point.longitude,

            history.forecast_time,
            history.pm2_5,
            history.pm10,
            history.carbon_monoxide,
            history.nitrogen_dioxide,
            history.sulphur_dioxide,
            history.ozone,
            history.us_aqi,
            history.us_aqi_pm2_5,
            history.us_aqi_pm10,
            history.us_aqi_nitrogen_dioxide,
            history.us_aqi_carbon_monoxide,
            history.us_aqi_ozone,
            history.us_aqi_sulphur_dioxide,
            history.aqi_level,
            history.aqi_severity,
            history.source,
            history.batch_id,
            history.schema_version,
            history.ingested_at

        FROM recent_history AS history

        INNER JOIN dim_monitoring_point AS point
            ON point.point_id =
                history.point_id

        INNER JOIN dim_location AS location
            ON location.location_id =
                history.location_id

        ORDER BY
            history.forecast_time
    """

    try:
        records = execute_query(
            query=query,
            parameters=(
                normalized_point_id,
                hours,
            ),
        )

    except (
        DatabaseConfigurationError,
        psycopg.Error,
    ) as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Không đọc được lịch sử "
                "chất lượng không khí: "
                f"{error}"
            ),
        ) from error

    if not records:
        raise HTTPException(
            status_code=404,
            detail=(
                "Không tìm thấy lịch sử AQI "
                "cho point_id "
                f"{normalized_point_id}."
            ),
        )

    return {
        "status": "SUCCESS",
        "point_id": (
            normalized_point_id
        ),
        "point_name": (
            records[0]["point_name"]
        ),
        "location_id": (
            records[0]["location_id"]
        ),
        "location_name": (
            records[0]["location_name"]
        ),
        "requested_hours": hours,
        "record_count": len(
            records
        ),
        "first_forecast_time": (
            records[0]["forecast_time"]
        ),
        "last_forecast_time": (
            records[-1]["forecast_time"]
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
            SELECT
                batch_id
            FROM fact_air_quality_hourly
            ORDER BY
                ingested_at DESC,
                batch_id DESC
            LIMIT 1
        )
        SELECT
            f.point_id,
            f.location_id,

            p.point_name,
            p.point_type,

            l.location_name,
            l.region,
            l.admin_type,

            p.latitude,
            p.longitude,

            f.forecast_time,
            f.pm2_5,
            f.pm10,
            f.carbon_monoxide,
            f.nitrogen_dioxide,
            f.sulphur_dioxide,
            f.ozone,
            f.us_aqi,
            f.source,
            f.batch_id,
            f.ingested_at

        FROM fact_air_quality_hourly AS f

        INNER JOIN dim_monitoring_point AS p
            ON p.point_id = f.point_id

        INNER JOIN dim_location AS l
            ON l.location_id = f.location_id

        WHERE f.batch_id = (
            SELECT batch_id
            FROM latest_batch
        )
          AND f.point_id = %s

        ORDER BY
            f.forecast_time

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