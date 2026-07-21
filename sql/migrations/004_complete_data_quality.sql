BEGIN;

DO $$
BEGIN
    IF to_regclass('public.pipeline_run_logs') IS NULL THEN
        RAISE EXCEPTION
            'Thiếu bảng public.pipeline_run_logs. Hãy chạy các migration nền trước migration 023.';
    END IF;

    IF to_regclass('public.data_quality_logs') IS NULL THEN
        RAISE EXCEPTION
            'Thiếu bảng public.data_quality_logs. Hãy chạy các migration nền trước migration 023.';
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS
    public.pipeline_run_logs_legacy_backup_step23 (
        backup_id BIGSERIAL PRIMARY KEY,
        original_run_id TEXT NOT NULL,
        backup_reason TEXT NOT NULL,
        backed_up_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        row_data JSONB NOT NULL
    );

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_pipeline_run_logs_legacy_backup_run_reason
ON public.pipeline_run_logs_legacy_backup_step23 (
    original_run_id,
    backup_reason
);

INSERT INTO public.pipeline_run_logs_legacy_backup_step23 (
    original_run_id,
    backup_reason,
    row_data
)
SELECT
    pipeline_log.run_id::TEXT,
    'STEP_23_MISSING_OR_BLANK_BATCH_OR_STAGE',
    TO_JSONB(pipeline_log)
FROM public.pipeline_run_logs AS pipeline_log
WHERE pipeline_log.batch_id IS NULL
   OR pipeline_log.stage_name IS NULL
   OR BTRIM(pipeline_log.batch_id) = ''
   OR BTRIM(pipeline_log.stage_name) = ''
ON CONFLICT (
    original_run_id,
    backup_reason
)
DO NOTHING;

DELETE FROM public.data_quality_logs AS quality_log
USING public.pipeline_run_logs AS pipeline_log
WHERE quality_log.run_id = pipeline_log.run_id
  AND (
      pipeline_log.batch_id IS NULL
      OR pipeline_log.stage_name IS NULL
      OR BTRIM(pipeline_log.batch_id) = ''
      OR BTRIM(pipeline_log.stage_name) = ''
  );

DELETE FROM public.pipeline_run_logs
WHERE batch_id IS NULL
   OR stage_name IS NULL
   OR BTRIM(batch_id) = ''
   OR BTRIM(stage_name) = '';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.pipeline_run_logs
        WHERE batch_id IS NULL
           OR stage_name IS NULL
           OR BTRIM(batch_id) = ''
           OR BTRIM(stage_name) = ''
    ) THEN
        RAISE EXCEPTION
            'pipeline_run_logs vẫn còn batch_id/stage_name NULL hoặc rỗng.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.data_quality_logs
        WHERE run_id IS NULL
           OR batch_id IS NULL
           OR check_name IS NULL
           OR BTRIM(run_id::TEXT) = ''
           OR BTRIM(batch_id) = ''
           OR BTRIM(check_name) = ''
    ) THEN
        RAISE EXCEPTION
            'data_quality_logs còn run_id/batch_id/check_name NULL hoặc rỗng.';
    END IF;
END
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM (
            SELECT
                batch_id,
                stage_name
            FROM public.pipeline_run_logs
            GROUP BY
                batch_id,
                stage_name
            HAVING COUNT(*) > 1
        ) AS duplicate_pipeline_logs
    ) THEN
        RAISE EXCEPTION
            'pipeline_run_logs có duplicate theo (batch_id, stage_name).';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM (
            SELECT
                batch_id,
                check_name
            FROM public.data_quality_logs
            GROUP BY
                batch_id,
                check_name
            HAVING COUNT(*) > 1
        ) AS duplicate_quality_batch_checks
    ) THEN
        RAISE EXCEPTION
            'data_quality_logs có duplicate theo (batch_id, check_name).';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM (
            SELECT
                run_id,
                check_name
            FROM public.data_quality_logs
            GROUP BY
                run_id,
                check_name
            HAVING COUNT(*) > 1
        ) AS duplicate_quality_run_checks
    ) THEN
        RAISE EXCEPTION
            'data_quality_logs có duplicate theo (run_id, check_name).';
    END IF;
END
$$;

ALTER TABLE public.pipeline_run_logs
    ALTER COLUMN batch_id SET NOT NULL,
    ALTER COLUMN stage_name SET NOT NULL;

ALTER TABLE public.data_quality_logs
    ALTER COLUMN run_id SET NOT NULL,
    ALTER COLUMN batch_id SET NOT NULL,
    ALTER COLUMN check_name SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.pipeline_run_logs'::REGCLASS
          AND conname = 'ck_pipeline_run_logs_batch_id_not_blank'
    ) THEN
        ALTER TABLE public.pipeline_run_logs
        ADD CONSTRAINT ck_pipeline_run_logs_batch_id_not_blank
        CHECK (
            BTRIM(batch_id) <> ''
        ) NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.pipeline_run_logs'::REGCLASS
          AND conname = 'ck_pipeline_run_logs_stage_name_not_blank'
    ) THEN
        ALTER TABLE public.pipeline_run_logs
        ADD CONSTRAINT ck_pipeline_run_logs_stage_name_not_blank
        CHECK (
            BTRIM(stage_name) <> ''
        ) NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.data_quality_logs'::REGCLASS
          AND conname = 'ck_data_quality_logs_run_id_not_blank'
    ) THEN
        ALTER TABLE public.data_quality_logs
        ADD CONSTRAINT ck_data_quality_logs_run_id_not_blank
        CHECK (
            BTRIM(run_id::TEXT) <> ''
        ) NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.data_quality_logs'::REGCLASS
          AND conname = 'ck_data_quality_logs_batch_id_not_blank'
    ) THEN
        ALTER TABLE public.data_quality_logs
        ADD CONSTRAINT ck_data_quality_logs_batch_id_not_blank
        CHECK (
            BTRIM(batch_id) <> ''
        ) NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.data_quality_logs'::REGCLASS
          AND conname = 'ck_data_quality_logs_check_name_not_blank'
    ) THEN
        ALTER TABLE public.data_quality_logs
        ADD CONSTRAINT ck_data_quality_logs_check_name_not_blank
        CHECK (
            BTRIM(check_name) <> ''
        ) NOT VALID;
    END IF;
END
$$;

ALTER TABLE public.pipeline_run_logs
    VALIDATE CONSTRAINT ck_pipeline_run_logs_batch_id_not_blank;

ALTER TABLE public.pipeline_run_logs
    VALIDATE CONSTRAINT ck_pipeline_run_logs_stage_name_not_blank;

ALTER TABLE public.data_quality_logs
    VALIDATE CONSTRAINT ck_data_quality_logs_run_id_not_blank;

ALTER TABLE public.data_quality_logs
    VALIDATE CONSTRAINT ck_data_quality_logs_batch_id_not_blank;

ALTER TABLE public.data_quality_logs
    VALIDATE CONSTRAINT ck_data_quality_logs_check_name_not_blank;

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_pipeline_run_logs_batch_stage
ON public.pipeline_run_logs (
    batch_id,
    stage_name
);

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_data_quality_logs_batch_check
ON public.data_quality_logs (
    batch_id,
    check_name
);

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_data_quality_run_check
ON public.data_quality_logs (
    run_id,
    check_name
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint AS constraint_row
        WHERE constraint_row.contype = 'f'
          AND constraint_row.conrelid =
              'public.data_quality_logs'::REGCLASS
          AND constraint_row.confrelid =
              'public.pipeline_run_logs'::REGCLASS
          AND POSITION(
              'FOREIGN KEY (run_id)'
              IN PG_GET_CONSTRAINTDEF(constraint_row.oid)
          ) > 0
          AND POSITION(
              'REFERENCES pipeline_run_logs(run_id)'
              IN PG_GET_CONSTRAINTDEF(constraint_row.oid)
          ) > 0
    ) THEN
        ALTER TABLE public.data_quality_logs
        ADD CONSTRAINT fk_data_quality_logs_pipeline_run
        FOREIGN KEY (
            run_id
        )
        REFERENCES public.pipeline_run_logs (
            run_id
        )
        ON UPDATE CASCADE
        ON DELETE CASCADE;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS
    idx_pipeline_run_logs_started_at
ON public.pipeline_run_logs (
    started_at DESC
);

CREATE INDEX IF NOT EXISTS
    idx_pipeline_run_logs_status_started_at
ON public.pipeline_run_logs (
    status,
    started_at DESC
);

CREATE INDEX IF NOT EXISTS
    idx_data_quality_logs_checked_at
ON public.data_quality_logs (
    checked_at DESC
);

CREATE INDEX IF NOT EXISTS
    idx_data_quality_logs_status_checked_at
ON public.data_quality_logs (
    status,
    checked_at DESC
);


COMMIT;