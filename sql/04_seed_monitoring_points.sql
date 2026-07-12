\set ON_ERROR_STOP on


INSERT INTO dim_monitoring_point (
    point_id,
    location_id,
    point_name,
    point_type,
    latitude,
    longitude,
    is_active
)
VALUES
    (
        'HN_CENTER',
        'HN',
        'Trung tâm Hà Nội',
        'urban_center',
        21.0285,
        105.8542,
        TRUE
    ),
    (
        'HCM_CENTER',
        'HCM',
        'Trung tâm TP.HCM',
        'urban_center',
        10.7769,
        106.7009,
        TRUE
    ),
    (
        'DN_CENTER',
        'DN',
        'Trung tâm Đà Nẵng',
        'urban_center',
        16.0544,
        108.2022,
        TRUE
    ),
    (
        'HP_CENTER',
        'HP',
        'Trung tâm Hải Phòng',
        'urban_center',
        20.8449,
        106.6881,
        TRUE
    ),
    (
        'CT_CENTER',
        'CT',
        'Trung tâm Cần Thơ',
        'urban_center',
        10.0452,
        105.7469,
        TRUE
    ),
    (
        'HUE_CENTER',
        'HUE',
        'Trung tâm Huế',
        'urban_center',
        16.4637,
        107.5909,
        TRUE
    ),
    (
        'QN_HA_LONG',
        'QN',
        'Hạ Long',
        'urban_center',
        20.9500,
        107.0667,
        TRUE
    ),
    (
        'KH_NHA_TRANG',
        'KH',
        'Nha Trang',
        'urban_center',
        12.2388,
        109.1967,
        TRUE
    ),
    (
        'LD_DA_LAT',
        'LD',
        'Đà Lạt',
        'urban_center',
        11.9404,
        108.4583,
        TRUE
    ),
    (
        'TH_CENTER',
        'TH',
        'Trung tâm Thanh Hóa',
        'urban_center',
        19.8067,
        105.7852,
        TRUE
    )
ON CONFLICT (point_id)
DO UPDATE SET
    location_id = EXCLUDED.location_id,
    point_name = EXCLUDED.point_name,
    point_type = EXCLUDED.point_type,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    is_active = EXCLUDED.is_active;