BEGIN;


CREATE TABLE IF NOT EXISTS dim_location (
    location_id VARCHAR(50) PRIMARY KEY,

    location_name VARCHAR(255) NOT NULL,

    region VARCHAR(100) NOT NULL,

    admin_type VARCHAR(100) NOT NULL,

    country_code VARCHAR(10)
        NOT NULL
        DEFAULT 'VN',

    timezone VARCHAR(100)
        NOT NULL
        DEFAULT 'Asia/Ho_Chi_Minh',

    is_active BOOLEAN
        NOT NULL
        DEFAULT TRUE,

    created_at TIMESTAMPTZ
        NOT NULL
        DEFAULT NOW(),

    updated_at TIMESTAMPTZ
        NOT NULL
        DEFAULT NOW(),

    CONSTRAINT chk_dim_location_id_not_blank
        CHECK (
            BTRIM(location_id) <> ''
        ),

    CONSTRAINT chk_dim_location_name_not_blank
        CHECK (
            BTRIM(location_name) <> ''
        )
);


CREATE TABLE IF NOT EXISTS dim_monitoring_point (
    point_id VARCHAR(100) PRIMARY KEY,

    location_id VARCHAR(50) NOT NULL,

    point_name VARCHAR(255) NOT NULL,

    point_type VARCHAR(100)
        NOT NULL
        DEFAULT 'urban_center',

    latitude DOUBLE PRECISION NOT NULL,

    longitude DOUBLE PRECISION NOT NULL,

    elevation_meters DOUBLE PRECISION,

    is_active BOOLEAN
        NOT NULL
        DEFAULT TRUE,

    created_at TIMESTAMPTZ
        NOT NULL
        DEFAULT NOW(),

    updated_at TIMESTAMPTZ
        NOT NULL
        DEFAULT NOW(),

    CONSTRAINT fk_monitoring_point_location
        FOREIGN KEY (
            location_id
        )
        REFERENCES dim_location (
            location_id
        ),

    CONSTRAINT chk_monitoring_point_id_not_blank
        CHECK (
            BTRIM(point_id) <> ''
        ),

    CONSTRAINT chk_monitoring_point_name_not_blank
        CHECK (
            BTRIM(point_name) <> ''
        ),

    CONSTRAINT chk_monitoring_point_latitude
        CHECK (
            latitude BETWEEN -90 AND 90
        ),

    CONSTRAINT chk_monitoring_point_longitude
        CHECK (
            longitude BETWEEN -180 AND 180
        )
);


CREATE INDEX IF NOT EXISTS
    idx_dim_location_active
ON dim_location (
    is_active
);


CREATE INDEX IF NOT EXISTS
    idx_dim_location_region
ON dim_location (
    region
);


CREATE INDEX IF NOT EXISTS
    idx_dim_monitoring_point_location
ON dim_monitoring_point (
    location_id
);


CREATE INDEX IF NOT EXISTS
    idx_dim_monitoring_point_active
ON dim_monitoring_point (
    is_active
);


CREATE INDEX IF NOT EXISTS
    idx_dim_monitoring_point_type
ON dim_monitoring_point (
    point_type
);


CREATE UNIQUE INDEX IF NOT EXISTS
    uq_dim_monitoring_point_coordinates
ON dim_monitoring_point (
    location_id,
    latitude,
    longitude
);


COMMIT;