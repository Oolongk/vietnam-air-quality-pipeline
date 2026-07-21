BEGIN;


DO $$
BEGIN
    IF to_regclass(
        'public.fact_air_quality_hourly'
    ) IS NULL THEN
        RAISE EXCEPTION
            'Thiếu bảng public.fact_air_quality_hourly.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'public'
          AND hypertable_name =
              'fact_air_quality_hourly'
    ) THEN
        RAISE EXCEPTION
            'public.fact_air_quality_hourly '
            'không phải TimescaleDB hypertable.';
    END IF;
END
$$;


DO $$
DECLARE
    required_column TEXT;
BEGIN
    FOREACH required_column IN ARRAY ARRAY[
        'batch_id',
        'ingested_at',
        'forecast_time',
        'point_id'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name =
                  'fact_air_quality_hourly'
              AND column_name =
                  required_column
        ) THEN
            RAISE EXCEPTION
                'fact_air_quality_hourly '
                'thiếu cột bắt buộc: %',
                required_column;
        END IF;
    END LOOP;
END
$$;


DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.fact_air_quality_hourly
        WHERE batch_id IS NULL
           OR BTRIM(batch_id) = ''
    ) THEN
        RAISE EXCEPTION
            'Không thể tạo API indexes vì '
            'fact_air_quality_hourly còn '
            'batch_id NULL hoặc rỗng.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.fact_air_quality_hourly
        WHERE ingested_at IS NULL
    ) THEN
        RAISE EXCEPTION
            'Không thể tạo API indexes vì '
            'fact_air_quality_hourly còn '
            'ingested_at NULL.';
    END IF;
END
$$;


CREATE INDEX IF NOT EXISTS
    idx_fact_aq_latest_ingestion
ON public.fact_air_quality_hourly (
    ingested_at DESC,
    batch_id DESC
);


CREATE INDEX IF NOT EXISTS
    idx_fact_aq_batch_forecast_point
ON public.fact_air_quality_hourly (
    batch_id,
    forecast_time,
    point_id
);


ANALYZE public.fact_air_quality_hourly;


COMMIT;