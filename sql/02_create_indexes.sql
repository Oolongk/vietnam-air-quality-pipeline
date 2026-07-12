\set ON_ERROR_STOP on


CREATE INDEX IF NOT EXISTS
    idx_air_quality_location_time
ON fact_air_quality_hourly (
    location_id,
    forecast_time DESC
);


CREATE INDEX IF NOT EXISTS
    idx_air_quality_point_time
ON fact_air_quality_hourly (
    point_id,
    forecast_time DESC
);


CREATE INDEX IF NOT EXISTS
    idx_air_quality_high_aqi
ON fact_air_quality_hourly (
    us_aqi DESC,
    forecast_time DESC
)
WHERE us_aqi >= 101;


CREATE INDEX IF NOT EXISTS
    idx_alert_location_time
ON fact_air_quality_alerts (
    location_id,
    alert_time DESC
);


CREATE INDEX IF NOT EXISTS
    idx_alert_status_time
ON fact_air_quality_alerts (
    status,
    alert_time DESC
);


CREATE INDEX IF NOT EXISTS
    idx_pipeline_run_started_at
ON pipeline_run_logs (
    started_at DESC
);


CREATE INDEX IF NOT EXISTS
    idx_pipeline_run_status
ON pipeline_run_logs (
    status,
    started_at DESC
);


CREATE INDEX IF NOT EXISTS
    idx_data_quality_run
ON data_quality_logs (
    run_id,
    created_at DESC
);


CREATE INDEX IF NOT EXISTS
    idx_monitoring_point_location
ON dim_monitoring_point (
    location_id,
    is_active
);