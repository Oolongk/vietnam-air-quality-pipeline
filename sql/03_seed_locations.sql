\set ON_ERROR_STOP on


INSERT INTO dim_location (
    location_id,
    location_name,
    region,
    admin_type,
    is_active
)
VALUES
    (
        'HN',
        'Hà Nội',
        'Miền Bắc',
        'Thành phố',
        TRUE
    ),
    (
        'HCM',
        'TP.HCM',
        'Miền Nam',
        'Thành phố',
        TRUE
    ),
    (
        'DN',
        'Đà Nẵng',
        'Miền Trung',
        'Thành phố',
        TRUE
    ),
    (
        'HP',
        'Hải Phòng',
        'Miền Bắc',
        'Thành phố',
        TRUE
    ),
    (
        'CT',
        'Cần Thơ',
        'Miền Nam',
        'Thành phố',
        TRUE
    ),
    (
        'HUE',
        'Huế',
        'Miền Trung',
        'Thành phố',
        TRUE
    ),
    (
        'QN',
        'Quảng Ninh',
        'Miền Bắc',
        'Tỉnh',
        TRUE
    ),
    (
        'KH',
        'Khánh Hòa',
        'Miền Trung',
        'Tỉnh',
        TRUE
    ),
    (
        'LD',
        'Lâm Đồng',
        'Miền Trung',
        'Tỉnh',
        TRUE
    ),
    (
        'TH',
        'Thanh Hóa',
        'Miền Bắc',
        'Tỉnh',
        TRUE
    )
ON CONFLICT (location_id)
DO UPDATE SET
    location_name = EXCLUDED.location_name,
    region = EXCLUDED.region,
    admin_type = EXCLUDED.admin_type,
    is_active = EXCLUDED.is_active;