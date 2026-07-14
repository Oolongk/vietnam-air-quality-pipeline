BEGIN;

CREATE TABLE IF NOT EXISTS pipeline_run_logs (
    log_id BIGSERIAL PRIMARY KEY,
    batch_id VARCHAR(100) NOT NULL,
    pipeline_name VARCHAR(150) NOT NULL,
    stage_name VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    duration_seconds DOUBLE PRECISION,
    input_records BIGINT,
    output_records BIGINT,
    failed_records BIGINT,
    summary_bucket VARCHAR(100),
    summary_object_name TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE pipeline_run_logs
    ADD COLUMN IF NOT EXISTS batch_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS pipeline_name VARCHAR(150),
    ADD COLUMN IF NOT EXISTS stage_name VARCHAR(50),
    ADD COLUMN IF NOT EXISTS status VARCHAR(30),
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS duration_seconds DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS input_records BIGINT,
    ADD COLUMN IF NOT EXISTS output_records BIGINT,
    ADD COLUMN IF NOT EXISTS failed_records BIGINT,
    ADD COLUMN IF NOT EXISTS summary_bucket VARCHAR(100),
    ADD COLUMN IF NOT EXISTS summary_object_name TEXT,
    ADD COLUMN IF NOT EXISTS error_message TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE UNIQUE INDEX IF NOT EXISTS
uq_pipeline_run_logs_batch_stage
ON pipeline_run_logs (
    batch_id,
    stage_name
);


CREATE TABLE IF NOT EXISTS data_quality_logs (
    log_id BIGSERIAL PRIMARY KEY,
    batch_id VARCHAR(100) NOT NULL,
    check_name VARCHAR(150) NOT NULL,
    status VARCHAR(30) NOT NULL,
    bad_records_count BIGINT NOT NULL DEFAULT 0,
    message TEXT,
    checked_at TIMESTAMPTZ,
    summary_bucket VARCHAR(100),
    summary_object_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE data_quality_logs
    ADD COLUMN IF NOT EXISTS batch_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS check_name VARCHAR(150),
    ADD COLUMN IF NOT EXISTS status VARCHAR(30),
    ADD COLUMN IF NOT EXISTS bad_records_count BIGINT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS message TEXT,
    ADD COLUMN IF NOT EXISTS checked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS summary_bucket VARCHAR(100),
    ADD COLUMN IF NOT EXISTS summary_object_name TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE UNIQUE INDEX IF NOT EXISTS
uq_data_quality_logs_batch_check
ON data_quality_logs (
    batch_id,
    check_name
);

COMMIT;