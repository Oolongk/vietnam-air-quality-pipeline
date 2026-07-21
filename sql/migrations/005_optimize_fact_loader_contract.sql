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
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'fact_air_quality_hourly'
          AND column_name = 'batch_id'
    ) THEN
        RAISE EXCEPTION
            'fact_air_quality_hourly thiếu cột batch_id.';
    END IF;
END
$$;


CREATE TABLE IF NOT EXISTS
    public.fact_air_quality_hourly_legacy_batch_backup_step24 (
        backup_id BIGSERIAL PRIMARY KEY,

        original_id BIGINT NOT NULL,
        original_forecast_time TIMESTAMPTZ NOT NULL,

        backup_reason TEXT NOT NULL,

        backed_up_at TIMESTAMPTZ
            NOT NULL DEFAULT NOW(),

        row_data JSONB NOT NULL
    );


CREATE UNIQUE INDEX IF NOT EXISTS
    uq_fact_aq_legacy_batch_backup_row_reason
ON public.fact_air_quality_hourly_legacy_batch_backup_step24 (
    original_id,
    original_forecast_time,
    backup_reason
);


INSERT INTO
    public.fact_air_quality_hourly_legacy_batch_backup_step24 (
        original_id,
        original_forecast_time,
        backup_reason,
        row_data
    )
SELECT
    fact_row.id,
    fact_row.forecast_time,
    'STEP_24_MISSING_OR_BLANK_BATCH_ID',
    TO_JSONB(fact_row)
FROM public.fact_air_quality_hourly AS fact_row
WHERE fact_row.batch_id IS NULL
   OR BTRIM(fact_row.batch_id) = ''
ON CONFLICT (
    original_id,
    original_forecast_time,
    backup_reason
)
DO NOTHING;


UPDATE public.fact_air_quality_hourly
SET batch_id = 'legacy_missing_batch_step24'
WHERE batch_id IS NULL
   OR BTRIM(batch_id) = '';


DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.fact_air_quality_hourly
        WHERE batch_id IS NULL
           OR BTRIM(batch_id) = ''
    ) THEN
        RAISE EXCEPTION
            'fact_air_quality_hourly vẫn còn batch_id NULL hoặc rỗng.';
    END IF;
END
$$;


ALTER TABLE public.fact_air_quality_hourly
    ALTER COLUMN batch_id SET NOT NULL;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid =
            'public.fact_air_quality_hourly'::REGCLASS
          AND conname =
            'ck_fact_air_quality_hourly_batch_id_not_blank'
    ) THEN
        ALTER TABLE public.fact_air_quality_hourly
        ADD CONSTRAINT
            ck_fact_air_quality_hourly_batch_id_not_blank
        CHECK (
            BTRIM(batch_id) <> ''
        )
        NOT VALID;
    END IF;
END
$$;


ALTER TABLE public.fact_air_quality_hourly
    VALIDATE CONSTRAINT
        ck_fact_air_quality_hourly_batch_id_not_blank;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid =
            'public.fact_air_quality_hourly'::REGCLASS
          AND conname =
            'uq_air_quality_point_time_source'
          AND contype = 'u'
    ) THEN
        RAISE EXCEPTION
            'Thiếu unique constraint chính '
            'uq_air_quality_point_time_source.';
    END IF;
END
$$;


-- Tạm giữ unique index dư thừa.
-- Đây là index của TimescaleDB hypertable và có các index tương ứng
-- trên từng chunk. Cleanup index sẽ được xử lý riêng sau khi kiểm tra
-- đầy đủ metadata của hypertable và chunk constraints.

COMMIT;