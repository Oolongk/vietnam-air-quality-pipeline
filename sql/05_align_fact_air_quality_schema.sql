BEGIN;

ALTER TABLE fact_air_quality_hourly
    ADD COLUMN IF NOT EXISTS us_aqi_pm2_5 INTEGER,
    ADD COLUMN IF NOT EXISTS us_aqi_pm10 INTEGER,
    ADD COLUMN IF NOT EXISTS us_aqi_nitrogen_dioxide INTEGER,
    ADD COLUMN IF NOT EXISTS us_aqi_carbon_monoxide INTEGER,
    ADD COLUMN IF NOT EXISTS us_aqi_ozone INTEGER,
    ADD COLUMN IF NOT EXISTS us_aqi_sulphur_dioxide INTEGER,
    ADD COLUMN IF NOT EXISTS batch_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS schema_version VARCHAR(20);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'fact_air_quality_hourly'
          AND column_name = 'point_id'
    ) THEN
        RAISE EXCEPTION
            'fact_air_quality_hourly thiếu cột point_id';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'fact_air_quality_hourly'
          AND column_name = 'forecast_time'
    ) THEN
        EXECUTE '
            CREATE UNIQUE INDEX IF NOT EXISTS
            uq_fact_air_quality_hourly_point_forecast_source
            ON fact_air_quality_hourly (
                point_id,
                forecast_time,
                source
            )
        ';

    ELSIF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'fact_air_quality_hourly'
          AND column_name = 'datetime'
    ) THEN
        EXECUTE '
            CREATE UNIQUE INDEX IF NOT EXISTS
            uq_fact_air_quality_hourly_point_datetime_source
            ON fact_air_quality_hourly (
                point_id,
                datetime,
                source
            )
        ';

    ELSE
        RAISE EXCEPTION
            'fact_air_quality_hourly thiếu forecast_time hoặc datetime';
    END IF;
END
$$;

COMMIT;