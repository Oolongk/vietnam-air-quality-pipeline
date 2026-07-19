BEGIN;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname =
            'fk_fact_air_quality_location'
    ) THEN
        ALTER TABLE
            fact_air_quality_hourly
        ADD CONSTRAINT
            fk_fact_air_quality_location
        FOREIGN KEY (
            location_id
        )
        REFERENCES dim_location (
            location_id
        )
        ON UPDATE CASCADE
        ON DELETE RESTRICT
        NOT VALID;
    END IF;
END
$$;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname =
            'fk_fact_air_quality_point'
    ) THEN
        ALTER TABLE
            fact_air_quality_hourly
        ADD CONSTRAINT
            fk_fact_air_quality_point
        FOREIGN KEY (
            point_id
        )
        REFERENCES dim_monitoring_point (
            point_id
        )
        ON UPDATE CASCADE
        ON DELETE RESTRICT
        NOT VALID;
    END IF;
END
$$;


ALTER TABLE fact_air_quality_hourly
VALIDATE CONSTRAINT
    fk_fact_air_quality_location;


ALTER TABLE fact_air_quality_hourly
VALIDATE CONSTRAINT
    fk_fact_air_quality_point;


COMMIT;