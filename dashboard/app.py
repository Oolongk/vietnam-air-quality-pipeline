from __future__ import annotations

from html import escape
import math
import os
from textwrap import dedent
from typing import Any

import altair as alt
import pandas as pd
import pydeck as pdk
from snapshot_client import (
    AirQualitySnapshotClient,
    AirQualitySnapshotError,
)
import streamlit as st

st.set_page_config(
    page_title="Chất lượng không khí Việt Nam",
    page_icon="🌏",
    layout="wide",
    initial_sidebar_state="collapsed",
)


VIETNAM_TIMEZONE = "Asia/Ho_Chi_Minh"
CARTO_LIGHT_MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"

NUMERIC_COLUMNS = [
    "latitude",
    "longitude",
    "pm2_5",
    "pm10",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
    "us_aqi",
    "us_aqi_pm2_5",
    "us_aqi_pm10",
    "us_aqi_nitrogen_dioxide",
    "us_aqi_carbon_monoxide",
    "us_aqi_ozone",
    "us_aqi_sulphur_dioxide",
    "duration_seconds",
    "input_records",
    "output_records",
    "failed_records",
    "bad_records_count",
    "aqi_value",
]

DATETIME_COLUMNS = [
    "forecast_time",
    "ingested_at",
    "created_at",
    "started_at",
    "finished_at",
    "checked_at",
    "updated_at",
    "alert_time",
    "acknowledged_at",
    "published_at",
    "generated_at",
]

POLLUTANT_LABELS = {
    "us_aqi": "Chỉ số AQI",
    "pm2_5": "PM2.5",
    "pm10": "PM10",
    "ozone": "O₃",
    "nitrogen_dioxide": "NO₂",
    "sulphur_dioxide": "SO₂",
    "carbon_monoxide": "CO",
}

POLLUTANT_UNITS = {
    "pm2_5": "µg/m³",
    "pm10": "µg/m³",
    "ozone": "µg/m³",
    "nitrogen_dioxide": "µg/m³",
    "sulphur_dioxide": "µg/m³",
    "carbon_monoxide": "µg/m³",
}

POINT_TYPE_LABELS = {
    "urban_center": "Trung tâm đô thị",
    "regional_center": "Trung tâm khu vực",
}

STAGE_LABELS = {
    "extract": "Thu thập dữ liệu",
    "transform": "Làm sạch dữ liệu",
    "data_quality": "Kiểm tra chất lượng",
    "load_timescaledb": "Lưu vào cơ sở dữ liệu",
    "alerts": "Xử lý cảnh báo",
    "mart": "Tạo dữ liệu tổng hợp",
    "snapshot_publish": "Xuất bản dữ liệu công khai",
}

STATUS_LABELS = {
    "SUCCESS": "Thành công",
    "HEALTHY": "Ổn định",
    "FAILED": "Thất bại",
    "FAIL": "Thất bại",
    "WARNING": "Cần chú ý",
    "RUNNING": "Đang chạy",
    "EMPTY": "Chưa có dữ liệu",
    "OPEN": "Đang mở",
    "ACKNOWLEDGED": "Đã xác nhận",
    "RESOLVED": "Đã xử lý",
    "PASS": "Đạt",
    "PASSED": "Đạt",
    "UNKNOWN": "Chưa xác định",
}

ALERT_SEVERITY_LABELS = {
    "MEDIUM": "Trung bình",
    "HIGH": "Cao",
    "CRITICAL": "Nghiêm trọng",
}

TIME_RANGE_OPTIONS = {
    "24 giờ": 24,
    "48 giờ": 48,
    "72 giờ": 72,
    "7 ngày": 168,
}

AQI_FILTER_OPTIONS = {
    "Hiển thị tất cả": None,
    "AQI trên 50": 50,
    "AQI trên 100": 100,
    "AQI trên 150": 150,
    "AQI trên 200": 200,
}

AQI_ORDER = [
    "Tốt",
    "Trung bình",
    "Không tốt cho nhóm nhạy cảm",
    "Không tốt",
    "Rất không tốt",
    "Nguy hiểm",
    "Không có dữ liệu",
]

AQI_BANDS = pd.DataFrame(
    [
        {
            "Mức AQI": "Tốt",
            "Từ": 0,
            "Đến": 50,
            "Màu": "#22c55e",
        },
        {
            "Mức AQI": "Trung bình",
            "Từ": 50,
            "Đến": 100,
            "Màu": "#eab308",
        },
        {
            "Mức AQI": "Không tốt cho nhóm nhạy cảm",
            "Từ": 100,
            "Đến": 150,
            "Màu": "#f97316",
        },
        {
            "Mức AQI": "Không tốt",
            "Từ": 150,
            "Đến": 200,
            "Màu": "#dc2626",
        },
        {
            "Mức AQI": "Rất không tốt",
            "Từ": 200,
            "Đến": 300,
            "Màu": "#9333ea",
        },
        {
            "Mức AQI": "Nguy hiểm",
            "Từ": 300,
            "Đến": 500,
            "Màu": "#7f1d1d",
        },
    ]
)


# -----------------------------------------------------------------------------
# Giao diện
# -----------------------------------------------------------------------------


def inject_dashboard_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --aq-primary: #0f766e;
            --aq-primary-dark: #115e59;
            --aq-secondary: #0284c7;
            --aq-background: #f4f7fb;
            --aq-surface: #ffffff;
            --aq-border: #dbe4ee;
            --aq-text: #172033;
            --aq-muted: #667085;
        }

        [data-testid="stSidebar"],
        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
        }

        [data-testid="stAppViewContainer"] {
            color: var(--aq-text);
            background:
                radial-gradient(
                    circle at top right,
                    rgba(14, 165, 233, 0.10),
                    transparent 28rem
                ),
                linear-gradient(
                    180deg,
                    #f8fbff 0%,
                    var(--aq-background) 100%
                );
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        [data-testid="stToolbar"] {
            right: 1rem;
        }

        .block-container {
            max-width: 1500px;
            padding-top: 1.4rem;
            padding-bottom: 3rem;
        }

        .aq-hero {
            position: relative;
            overflow: hidden;
            padding: 2rem 2.2rem;
            margin-bottom: 1.2rem;
            border: 1px solid rgba(255, 255, 255, 0.55);
            border-radius: 24px;
            color: white;
            background:
                linear-gradient(
                    135deg,
                    #0f766e 0%,
                    #0369a1 58%,
                    #1d4ed8 100%
                );
            box-shadow: 0 20px 45px rgba(15, 118, 110, 0.18);
        }

        .aq-hero::after {
            content: "";
            position: absolute;
            width: 260px;
            height: 260px;
            right: -80px;
            top: -110px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.12);
        }

        .aq-hero__eyebrow {
            position: relative;
            z-index: 1;
            margin-bottom: 0.55rem;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: rgba(255, 255, 255, 0.80);
        }

        .aq-hero__title {
            position: relative;
            z-index: 1;
            margin: 0;
            color: white;
            font-size: clamp(2rem, 4vw, 3.35rem);
            font-weight: 750;
            line-height: 1.08;
            letter-spacing: -0.035em;
        }

        .aq-hero__description {
            position: relative;
            z-index: 1;
            max-width: 920px;
            margin-top: 0.9rem;
            margin-bottom: 0;
            color: rgba(255, 255, 255, 0.92);
            font-size: 1rem;
            line-height: 1.7;
        }

        .aq-toolbar-note {
            min-height: 2.75rem;
            padding: 0.65rem 0.9rem;
            border: 1px solid var(--aq-border);
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.92);
            color: #475467;
            line-height: 1.45;
        }

        .aq-legend {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem 1rem;
            margin: 0.35rem 0 1rem 0;
            color: #475467;
            font-size: 0.85rem;
        }

        .aq-legend__item {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
        }

        .aq-legend__dot {
            width: 0.72rem;
            height: 0.72rem;
            border-radius: 999px;
            border: 1px solid rgba(15, 23, 42, 0.15);
        }

        .aq-advice {
            padding: 1rem 1.05rem;
            margin: 0.7rem 0;
            border: 1px solid var(--aq-border);
            border-left: 5px solid var(--advice-color, #0284c7);
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.94);
        }

        .aq-advice__title {
            margin-bottom: 0.3rem;
            color: var(--aq-text);
            font-weight: 750;
        }

        .aq-advice__body {
            color: #475467;
            line-height: 1.6;
        }

        .aq-footer {
            margin-top: 2.5rem;
            padding-top: 1rem;
            border-top: 1px solid var(--aq-border);
            color: var(--aq-muted);
            font-size: 0.84rem;
            line-height: 1.65;
        }

        div[data-testid="stMetric"] {
            min-height: 120px;
            padding: 1.05rem 1.15rem;
            border: 1px solid var(--aq-border);
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.94);
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.055);
        }

        div[data-testid="stMetricLabel"],
        div[data-testid="stMetricLabel"] p {
            color: #475467;
            opacity: 1;
            font-weight: 600;
        }

        div[data-testid="stMetricValue"] {
            color: var(--aq-text);
            font-weight: 720;
        }

        div[data-testid="stDataFrame"] {
            overflow: hidden;
            border: 1px solid var(--aq-border);
            border-radius: 16px;
            background: var(--aq-surface);
        }

        div[data-testid="stPlotlyChart"],
        div[data-testid="stVegaLiteChart"],
        div[data-testid="stArrowVegaLiteChart"],
        div[data-testid="stDeckGlJsonChart"] {
            padding: 0.45rem;
            border: 1px solid var(--aq-border);
            border-radius: 18px;
            background: var(--aq-surface);
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
        }

        div[data-testid="stTabs"] button[role="tab"] {
            height: 3rem;
            padding-left: 1rem;
            padding-right: 1rem;
            color: #475467;
            opacity: 1;
            font-weight: 650;
        }

        div[data-testid="stTabs"] button[role="tab"] p {
            color: inherit;
            opacity: 1;
        }

        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            color: var(--aq-primary);
        }

        div[data-testid="stAlert"] {
            border-radius: 16px;
        }

        .stButton > button,
        .stDownloadButton > button {
            min-height: 2.75rem;
            border-radius: 12px;
            font-weight: 650;
        }

        .stSelectbox div[data-baseweb="select"] > div,
        .stTextInput div[data-baseweb="input"],
        .stMultiSelect div[data-baseweb="select"] > div {
            border-radius: 12px;
        }

        h1,
        h2,
        h3 {
            color: var(--aq-text);
            letter-spacing: -0.02em;
        }

        @media (max-width: 768px) {
            .block-container {
                padding-left: 0.85rem;
                padding-right: 0.85rem;
            }

            .aq-hero {
                padding: 1.4rem;
                border-radius: 18px;
            }

            .aq-hero__title {
                font-size: 1.9rem;
            }

            .aq-hero__description {
                font-size: 0.94rem;
            }

            div[data-testid="stMetric"] {
                min-height: 104px;
                padding: 0.85rem;
            }

            div[data-testid="stTabs"] button[role="tab"] {
                padding-left: 0.65rem;
                padding-right: 0.65rem;
                font-size: 0.88rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard_header() -> None:
    st.markdown(
        dedent(
            """
            <section class="aq-hero">
                <div class="aq-hero__eyebrow">
                    Vietnam Air Quality
                </div>
                <h1 class="aq-hero__title">
                    Chất lượng không khí trên toàn Việt Nam
                </h1>
                <p class="aq-hero__description">
                    Theo dõi chỉ số AQI và các chất ô nhiễm tại 102 vị trí đại
                    diện thuộc 34 tỉnh, thành phố. Dữ liệu được hệ thống tự động
                    thu thập, kiểm tra và cập nhật định kỳ.
                </p>
            </section>
            """
        ).strip(),
        unsafe_allow_html=True,
    )


def render_aqi_legend() -> None:
    st.markdown(
        """
        <div class="aq-legend">
            <span class="aq-legend__item">
                <span class="aq-legend__dot" style="background:#22c55e"></span>
                Tốt
            </span>
            <span class="aq-legend__item">
                <span class="aq-legend__dot" style="background:#eab308"></span>
                Trung bình
            </span>
            <span class="aq-legend__item">
                <span class="aq-legend__dot" style="background:#f97316"></span>
                Không tốt cho nhóm nhạy cảm
            </span>
            <span class="aq-legend__item">
                <span class="aq-legend__dot" style="background:#dc2626"></span>
                Không tốt
            </span>
            <span class="aq-legend__item">
                <span class="aq-legend__dot" style="background:#9333ea"></span>
                Rất không tốt
            </span>
            <span class="aq-legend__item">
                <span class="aq-legend__dot" style="background:#7f1d1d"></span>
                Nguy hiểm
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_glossary_and_footer() -> None:
    st.markdown("---")
    st.subheader("Giải thích các thuật ngữ")

    with st.expander(
        "Chỉ số chất lượng không khí và các chất ô nhiễm",
        expanded=False,
    ):
        st.markdown(
            """
            **AQI** là chỉ số giúp mô tả chất lượng không khí bằng một con số.
            Số càng cao thì mức độ ô nhiễm và nguy cơ ảnh hưởng sức khỏe càng lớn.

            **PM2.5** là bụi mịn có đường kính rất nhỏ, có thể đi sâu vào đường hô hấp.

            **PM10** là nhóm hạt bụi có kích thước lớn hơn PM2.5 nhưng vẫn có thể
            ảnh hưởng đến hệ hô hấp.

            **O₃** là ozone gần mặt đất. Nồng độ cao có thể gây kích ứng đường hô hấp.

            **NO₂** là nitrogen dioxide, thường liên quan đến giao thông và quá trình
            đốt nhiên liệu.

            **SO₂** là sulphur dioxide, thường phát sinh từ việc đốt nhiên liệu có
            chứa lưu huỳnh.

            **CO** là carbon monoxide, một loại khí sinh ra khi nhiên liệu cháy
            không hoàn toàn.
            """
        )

    with st.expander(
        "Dữ liệu và cách hệ thống hoạt động",
        expanded=False,
    ):
        st.markdown(
            """
            **Điểm theo dõi** là một tọa độ đại diện được dùng để lấy dữ liệu mô hình.
            Đây không nhất thiết là vị trí của một trạm đo vật lý.

            **Dữ liệu dự báo** là giá trị do mô hình ước tính cho các giờ tiếp theo,
            không phải số đo trực tiếp tại hiện trường.

            **Bản ghi** là một dòng dữ liệu cho một điểm và một thời điểm.

            **Mã lần xử lý** dùng để nhận biết dữ liệu được tạo trong lần chạy nào
            của hệ thống.

            **Kiểm tra chất lượng dữ liệu** là các bước phát hiện dữ liệu thiếu,
            sai kiểu, âm bất thường hoặc trùng lặp.

            **Bản dữ liệu công khai** là bộ JSON được chuẩn bị riêng cho website,
            giúp website không phải kết nối trực tiếp tới cơ sở dữ liệu.

            **Quy trình xử lý** là chuỗi bước tự động từ thu thập, làm sạch, kiểm tra,
            lưu trữ, tổng hợp đến xuất bản dữ liệu.
            """
        )

    st.markdown(
        """
        <div class="aq-footer">
            Dữ liệu Open-Meteo là dữ liệu mô hình và dự báo theo tọa độ đại diện,
            không phải dữ liệu đo trực tiếp từ trạm quan trắc tại mọi khu vực.
            Thông tin và khuyến nghị trên website chỉ mang tính tham khảo, không
            thay thế cảnh báo môi trường hoặc hướng dẫn y tế chính thức.
        </div>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# Xử lý dữ liệu
# -----------------------------------------------------------------------------


def clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback

    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass

    normalized = str(value).strip()
    return normalized or fallback


def classify_aqi(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "Không có dữ liệu"

    aqi = float(value)
    if aqi <= 50:
        return "Tốt"
    if aqi <= 100:
        return "Trung bình"
    if aqi <= 150:
        return "Không tốt cho nhóm nhạy cảm"
    if aqi <= 200:
        return "Không tốt"
    if aqi <= 300:
        return "Rất không tốt"
    return "Nguy hiểm"


def get_aqi_color(value: float | int | None) -> list[int]:
    if value is None or pd.isna(value):
        return [148, 163, 184, 210]

    aqi = float(value)
    if aqi <= 50:
        return [34, 197, 94, 225]
    if aqi <= 100:
        return [234, 179, 8, 230]
    if aqi <= 150:
        return [249, 115, 22, 230]
    if aqi <= 200:
        return [220, 38, 38, 230]
    if aqi <= 300:
        return [147, 51, 234, 230]
    return [127, 29, 29, 235]


def get_health_recommendation(
    value: float | int | None,
) -> tuple[str, str, str]:
    level = classify_aqi(value)

    recommendations = {
        "Tốt": (
            "Sinh hoạt ngoài trời bình thường",
            "Chất lượng không khí đang ở mức tốt. Hầu hết mọi người có thể "
            "sinh hoạt và vận động ngoài trời như bình thường.",
            "#22c55e",
        ),
        "Trung bình": (
            "Hầu hết mọi người có thể sinh hoạt bình thường",
            "Người đặc biệt nhạy cảm nên theo dõi cơ thể và giảm hoạt động "
            "kéo dài ngoài trời nếu cảm thấy khó chịu.",
            "#eab308",
        ),
        "Không tốt cho nhóm nhạy cảm": (
            "Nhóm nhạy cảm nên giảm hoạt động ngoài trời",
            "Trẻ em, người lớn tuổi và người có bệnh tim hoặc hô hấp nên "
            "giảm hoạt động kéo dài hoặc gắng sức ngoài trời.",
            "#f97316",
        ),
        "Không tốt": (
            "Nên giảm thời gian vận động ngoài trời",
            "Mọi người nên giảm hoạt động kéo dài hoặc gắng sức ngoài trời. "
            "Nhóm nhạy cảm cần hạn chế nhiều hơn.",
            "#dc2626",
        ),
        "Rất không tốt": (
            "Hạn chế ra ngoài khi không cần thiết",
            "Nên tránh vận động gắng sức ngoài trời. Nhóm nhạy cảm nên ở "
            "trong nhà khi có thể và theo dõi khuyến cáo chính thức.",
            "#9333ea",
        ),
        "Nguy hiểm": (
            "Tránh hoạt động ngoài trời",
            "Mọi người nên tránh hoạt động ngoài trời và theo dõi cảnh báo "
            "môi trường hoặc hướng dẫn y tế chính thức.",
            "#7f1d1d",
        ),
        "Không có dữ liệu": (
            "Chưa thể đưa ra khuyến nghị",
            "Hiện chưa có đủ dữ liệu AQI để đánh giá mức chất lượng không khí.",
            "#64748b",
        ),
    }

    title, body, color = recommendations[level]
    return title, body, color


def render_health_recommendation(value: float | int | None) -> None:
    title, body, color = get_health_recommendation(value)
    st.markdown(
        (
            f'<div class="aq-advice" style="--advice-color:{color}">'
            f'<div class="aq-advice__title">{escape(title)}</div>'
            f'<div class="aq-advice__body">{escape(body)}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def format_number(value: Any, decimal_places: int = 1) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.{decimal_places}f}"


def format_integer(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{int(float(value)):,}"


def parse_timestamp(value: Any) -> pd.Timestamp | None:
    if value is None or value == "":
        return None

    try:
        timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    except (TypeError, ValueError):
        return None

    if timestamp is None or pd.isna(timestamp):
        return None

    return pd.Timestamp(timestamp)


def format_datetime(value: Any) -> str:
    timestamp = parse_timestamp(value)
    if timestamp is None:
        return "N/A"

    return timestamp.tz_convert(VIETNAM_TIMEZONE).strftime("%d/%m/%Y %H:%M")


def format_relative_age(value: pd.Timestamp | None) -> str:
    if value is None:
        return "chưa xác định được độ mới"

    age_seconds = max(
        0,
        int((pd.Timestamp.now(tz="UTC") - value.tz_convert("UTC")).total_seconds()),
    )

    if age_seconds < 60:
        return "vừa cập nhật"

    minutes = age_seconds // 60
    if minutes < 60:
        return f"cách đây {minutes} phút"

    hours = minutes // 60
    if hours < 24:
        return f"cách đây {hours} giờ"

    days = hours // 24
    return f"cách đây {days} ngày"


def get_data_age_minutes(value: pd.Timestamp | None) -> int | None:
    if value is None:
        return None

    return max(
        0,
        int(
            (pd.Timestamp.now(tz="UTC") - value.tz_convert("UTC")).total_seconds() // 60
        ),
    )


def get_data_updated_at(
    latest_payload: dict[str, Any],
    health_payload: dict[str, Any],
    dataframe: pd.DataFrame,
) -> pd.Timestamp | None:
    fields = [
        "published_at",
        "generated_at",
        "snapshot_created_at",
        "updated_at",
        "created_at",
        "finished_at",
    ]

    timestamps: list[pd.Timestamp] = []

    for payload in [latest_payload, health_payload]:
        for field_name in fields:
            timestamp = parse_timestamp(payload.get(field_name))
            if timestamp is not None:
                timestamps.append(timestamp)

    if "ingested_at" in dataframe.columns:
        ingested_at = pd.to_datetime(
            dataframe["ingested_at"],
            errors="coerce",
            utc=True,
        ).max()
        if ingested_at is not None and not pd.isna(ingested_at):
            timestamps.append(pd.Timestamp(ingested_at))

    if not timestamps:
        return None

    return max(timestamps)


def format_delta(value: float | int | None) -> str | None:
    if value is None or pd.isna(value):
        return None

    rounded = round(float(value), 1)
    if rounded == 0:
        return "Không đổi so với giờ trước"
    if rounded > 0:
        return f"Tăng {abs(rounded):.1f} so với giờ trước"
    return f"Giảm {abs(rounded):.1f} so với giờ trước"


def translate_point_type(value: Any) -> str:
    normalized = clean_text(value)
    return POINT_TYPE_LABELS.get(
        normalized,
        normalized or "Chưa phân loại",
    )


def translate_stage(value: Any) -> str:
    normalized = clean_text(value)
    return STAGE_LABELS.get(
        normalized,
        normalized or "Chưa xác định",
    )


def translate_status(value: Any) -> str:
    normalized = clean_text(value).upper()
    return STATUS_LABELS.get(
        normalized,
        normalized or "Chưa xác định",
    )


def translate_alert_severity(value: Any) -> str:
    normalized = clean_text(value).upper()
    return ALERT_SEVERITY_LABELS.get(
        normalized,
        normalized or "Chưa xác định",
    )


def records_to_dataframe(
    records: list[dict[str, Any]],
) -> pd.DataFrame:
    dataframe = pd.DataFrame(records)
    if dataframe.empty:
        return dataframe

    for column in NUMERIC_COLUMNS:
        if column in dataframe.columns:
            dataframe[column] = pd.to_numeric(
                dataframe[column],
                errors="coerce",
            )

    for column in DATETIME_COLUMNS:
        if column in dataframe.columns:
            dataframe[column] = pd.to_datetime(
                dataframe[column],
                errors="coerce",
                utc=True,
            )

    for column in ["point_id", "location_id", "batch_id"]:
        if column in dataframe.columns:
            dataframe[column] = (
                dataframe[column]
                .where(dataframe[column].notna(), "")
                .astype(str)
                .str.strip()
            )

    return dataframe


def first_non_empty_value(values: pd.Series) -> str:
    for value in values:
        normalized = clean_text(value)
        if normalized:
            return normalized
    return ""


def select_nearest_forecast_records(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()

    working = dataframe.copy()
    if "point_id" not in working.columns:
        return working

    if "forecast_time" not in working.columns:
        return working.drop_duplicates(
            subset=["point_id"],
            keep="first",
        )

    now_utc = pd.Timestamp.now(tz="UTC")
    working["_forecast_distance"] = (working["forecast_time"] - now_utc).abs()

    working = working.sort_values(
        by=[
            "point_id",
            "_forecast_distance",
            "forecast_time",
        ],
        ascending=[True, True, True],
        na_position="last",
    )

    return (
        working.drop_duplicates(
            subset=["point_id"],
            keep="first",
        )
        .drop(
            columns=["_forecast_distance"],
            errors="ignore",
        )
        .reset_index(drop=True)
    )


def build_location_summary_dataframe(
    nearest_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    if nearest_dataframe.empty:
        return pd.DataFrame()

    working = nearest_dataframe.copy()

    required_defaults: dict[str, Any] = {
        "location_id": "",
        "location_name": "",
        "point_id": "",
        "point_name": "",
        "latitude": pd.NA,
        "longitude": pd.NA,
        "us_aqi": pd.NA,
        "pm2_5": pd.NA,
        "pm10": pd.NA,
        "ozone": pd.NA,
        "nitrogen_dioxide": pd.NA,
        "forecast_time": pd.NaT,
    }

    for column_name, default_value in required_defaults.items():
        if column_name not in working.columns:
            working[column_name] = default_value

    working["location_id"] = (
        working["location_id"]
        .where(working["location_id"].notna(), "")
        .astype(str)
        .str.strip()
    )
    working = working.loc[working["location_id"].ne("")].copy()

    for column_name in [
        "latitude",
        "longitude",
        "us_aqi",
        "pm2_5",
        "pm10",
        "ozone",
        "nitrogen_dioxide",
    ]:
        working[column_name] = pd.to_numeric(
            working[column_name],
            errors="coerce",
        )

    summary = working.groupby(
        "location_id",
        as_index=False,
        dropna=False,
    ).agg(
        location_name=(
            "location_name",
            first_non_empty_value,
        ),
        latitude=("latitude", "mean"),
        longitude=("longitude", "mean"),
        monitoring_point_count=("point_id", "nunique"),
        average_us_aqi=("us_aqi", "mean"),
        maximum_us_aqi=("us_aqi", "max"),
        average_pm2_5=("pm2_5", "mean"),
        average_pm10=("pm10", "mean"),
        average_ozone=("ozone", "mean"),
        average_nitrogen_dioxide=(
            "nitrogen_dioxide",
            "mean",
        ),
        forecast_time=("forecast_time", "max"),
    )

    worst_points = (
        working.sort_values(
            ["location_id", "us_aqi", "point_id"],
            ascending=[True, False, True],
            na_position="last",
        )
        .drop_duplicates(
            "location_id",
            keep="first",
        )[
            [
                "location_id",
                "point_id",
                "point_name",
                "us_aqi",
            ]
        ]
        .rename(
            columns={
                "point_id": "worst_point_id",
                "point_name": "worst_point_name",
                "us_aqi": "worst_point_us_aqi",
            }
        )
    )

    summary = summary.merge(
        worst_points,
        on="location_id",
        how="left",
        validate="1:1",
    )

    summary["location_label"] = summary.apply(
        lambda row: clean_text(
            row.get("location_name"),
            clean_text(
                row.get("location_id"),
                "Không rõ",
            ),
        ),
        axis=1,
    )
    summary["aqi_level"] = summary["average_us_aqi"].apply(classify_aqi)
    summary["fill_color"] = summary["average_us_aqi"].apply(get_aqi_color)
    summary["marker_radius"] = (
        summary["average_us_aqi"].fillna(0).clip(lower=0, upper=300).mul(110).add(22000)
    )

    round_columns = [
        "average_us_aqi",
        "maximum_us_aqi",
        "average_pm2_5",
        "average_pm10",
        "average_ozone",
        "average_nitrogen_dioxide",
        "latitude",
        "longitude",
    ]
    summary[round_columns] = summary[round_columns].round(2)

    return summary.sort_values(
        ["average_us_aqi", "maximum_us_aqi"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)


def prepare_mart_location_summary_dataframe(
    records: list[dict[str, Any]],
) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()

    dataframe = pd.DataFrame(records)
    defaults: dict[str, Any] = {
        "location_id": "",
        "location_name": "",
        "latitude": pd.NA,
        "longitude": pd.NA,
        "monitoring_point_count": 0,
        "average_us_aqi": pd.NA,
        "maximum_us_aqi": pd.NA,
        "average_pm2_5": pd.NA,
        "average_pm10": pd.NA,
        "average_ozone": pd.NA,
        "average_nitrogen_dioxide": pd.NA,
        "worst_point_id": "",
        "worst_point_name": "",
        "worst_point_us_aqi": pd.NA,
        "forecast_time": pd.NaT,
    }
    for column_name, default_value in defaults.items():
        if column_name not in dataframe.columns:
            dataframe[column_name] = default_value

    dataframe["location_id"] = (
        dataframe["location_id"]
        .where(dataframe["location_id"].notna(), "")
        .astype(str)
        .str.strip()
    )
    dataframe = dataframe.loc[dataframe["location_id"].ne("")].copy()
    numeric_columns = [
        "latitude",
        "longitude",
        "monitoring_point_count",
        "average_us_aqi",
        "maximum_us_aqi",
        "average_pm2_5",
        "average_pm10",
        "average_ozone",
        "average_nitrogen_dioxide",
        "worst_point_us_aqi",
    ]
    for column_name in numeric_columns:
        dataframe[column_name] = pd.to_numeric(
            dataframe[column_name],
            errors="coerce",
        )
    dataframe["forecast_time"] = pd.to_datetime(
        dataframe["forecast_time"],
        errors="coerce",
        utc=True,
    )
    dataframe["location_label"] = dataframe.apply(
        lambda row: clean_text(
            row.get("location_name"),
            clean_text(row.get("location_id"), "Không rõ"),
        ),
        axis=1,
    )
    if "aqi_level" not in dataframe.columns:
        dataframe["aqi_level"] = dataframe["average_us_aqi"].apply(classify_aqi)
    dataframe["fill_color"] = dataframe["average_us_aqi"].apply(get_aqi_color)
    dataframe["marker_radius"] = (
        dataframe["average_us_aqi"]
        .fillna(0)
        .clip(lower=0, upper=300)
        .mul(110)
        .add(22000)
    )
    round_columns = [
        "average_us_aqi",
        "maximum_us_aqi",
        "average_pm2_5",
        "average_pm10",
        "average_ozone",
        "average_nitrogen_dioxide",
        "latitude",
        "longitude",
    ]
    dataframe[round_columns] = dataframe[round_columns].round(2)
    return dataframe.sort_values(
        ["average_us_aqi", "maximum_us_aqi"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)


def get_selected_location_from_map(
    map_event: Any,
) -> str | None:
    if map_event is None:
        return None

    selection = getattr(
        map_event,
        "selection",
        None,
    )
    if selection is None and hasattr(map_event, "get"):
        selection = map_event.get("selection")
    if not selection:
        return None

    objects = getattr(selection, "objects", None)
    if objects is None and hasattr(selection, "get"):
        objects = selection.get("objects", {})
    if not objects or not hasattr(objects, "get"):
        return None

    selected_objects = objects.get(
        "location-markers",
        [],
    )
    if not selected_objects:
        return None

    location_id = clean_text(selected_objects[0].get("location_id"))
    return location_id or None


def calculate_available_time_hours(
    dataframe: pd.DataFrame,
    time_column: str = "forecast_time",
) -> int:
    if dataframe.empty or time_column not in dataframe.columns:
        return 24

    timestamps = (
        pd.to_datetime(
            dataframe[time_column],
            errors="coerce",
            utc=True,
        )
        .dropna()
        .sort_values()
        .drop_duplicates()
    )

    if timestamps.empty:
        return 24

    if len(timestamps) == 1:
        return 1

    available_hours = (
        int(round((timestamps.iloc[-1] - timestamps.iloc[0]).total_seconds() / 3600))
        + 1
    )

    return max(1, available_hours)


def filter_by_time_range(
    dataframe: pd.DataFrame,
    hours: int,
    time_column: str = "forecast_time",
) -> pd.DataFrame:
    if dataframe.empty or time_column not in dataframe.columns:
        return dataframe.copy()

    working = dataframe.copy()
    working[time_column] = pd.to_datetime(
        working[time_column],
        errors="coerce",
        utc=True,
    )
    working = working.dropna(subset=[time_column]).sort_values(time_column).copy()

    if working.empty:
        return working

    now_utc = pd.Timestamp.now(tz="UTC")
    start_time = now_utc - pd.Timedelta(hours=1)
    end_time = now_utc + pd.Timedelta(hours=hours)

    filtered = working.loc[
        working[time_column].between(
            start_time,
            end_time,
            inclusive="both",
        )
    ].copy()

    if not filtered.empty:
        return filtered

    # Khi snapshot nằm ngoài thời điểm hiện tại, dùng cửa sổ mới nhất
    # nhưng vẫn giữ dữ liệu của tất cả tỉnh và điểm theo dõi.
    latest_time = working[time_column].max()
    fallback_start = latest_time - pd.Timedelta(hours=max(hours - 1, 0))

    return working.loc[
        working[time_column].between(
            fallback_start,
            latest_time,
            inclusive="both",
        )
    ].copy()


def calculate_nearest_hour_delta(
    dataframe: pd.DataFrame,
    value_column: str,
) -> float | None:
    required_columns = {"forecast_time", value_column}
    if dataframe.empty or not required_columns.issubset(dataframe.columns):
        return None

    hourly = (
        dataframe[["forecast_time", value_column]]
        .dropna()
        .groupby("forecast_time")[value_column]
        .mean()
        .sort_index()
    )

    if len(hourly) < 2:
        return None

    now_utc = pd.Timestamp.now(tz="UTC")
    distances = (hourly.index.to_series() - now_utc).abs()
    nearest_position = int(distances.to_numpy().argmin())

    if nearest_position == 0:
        return None

    return float(hourly.iloc[nearest_position] - hourly.iloc[nearest_position - 1])


def to_vietnam_local_naive(
    values: pd.Series,
) -> pd.Series:
    timestamps = pd.to_datetime(
        values,
        errors="coerce",
        utc=True,
    )
    return timestamps.dt.tz_convert(VIETNAM_TIMEZONE).dt.tz_localize(None)


def build_aqi_chart(
    dataframe: pd.DataFrame,
    series_column: str | None = None,
    height: int = 420,
) -> alt.LayerChart:
    working = dataframe.copy()
    required = {"forecast_time", "us_aqi"}
    if working.empty or not required.issubset(working.columns):
        empty_dataframe = pd.DataFrame(
            {
                "Thời gian": [],
                "Chỉ số AQI": [],
            }
        )
        return (
            alt.Chart(empty_dataframe)
            .mark_line()
            .encode(
                x="Thời gian:T",
                y="Chỉ số AQI:Q",
            )
            .properties(height=height)
        )

    working = working.dropna(subset=["forecast_time", "us_aqi"]).copy()
    working["Thời gian"] = to_vietnam_local_naive(working["forecast_time"])
    working["Chỉ số AQI"] = pd.to_numeric(
        working["us_aqi"],
        errors="coerce",
    )

    grouping_columns = ["Thời gian"]
    if series_column and series_column in working.columns:
        working["Khu vực"] = working[series_column].astype(str)
        grouping_columns.append("Khu vực")

    working = (
        working.groupby(
            grouping_columns,
            as_index=False,
        )["Chỉ số AQI"]
        .mean()
        .sort_values("Thời gian")
    )

    observed_maximum = working["Chỉ số AQI"].max()
    if pd.isna(observed_maximum):
        chart_maximum = 150
    else:
        chart_maximum = int(
            min(
                500,
                max(
                    100,
                    math.ceil((float(observed_maximum) + 25) / 50) * 50,
                ),
            )
        )

    visible_bands = AQI_BANDS.copy()
    visible_bands["Đến"] = visible_bands["Đến"].clip(upper=chart_maximum)
    visible_bands = visible_bands.loc[visible_bands["Từ"].lt(chart_maximum)].copy()

    bands = (
        alt.Chart(visible_bands)
        .mark_rect(opacity=0.10)
        .encode(
            y=alt.Y(
                "Từ:Q",
                scale=alt.Scale(domain=[0, chart_maximum]),
                title="Chỉ số AQI",
            ),
            y2="Đến:Q",
            color=alt.Color(
                "Mức AQI:N",
                scale=alt.Scale(
                    domain=AQI_BANDS["Mức AQI"].tolist(),
                    range=AQI_BANDS["Màu"].tolist(),
                ),
                legend=None,
            ),
        )
    )

    tooltip = [
        alt.Tooltip(
            "Thời gian:T",
            title="Thời gian Việt Nam",
            format="%d/%m/%Y %H:%M",
        ),
        alt.Tooltip(
            "Chỉ số AQI:Q",
            title="AQI",
            format=".1f",
        ),
    ]

    if "Khu vực" in working.columns:
        tooltip.insert(
            1,
            alt.Tooltip(
                "Khu vực:N",
                title="Tỉnh/thành",
            ),
        )
        line = (
            alt.Chart(working)
            .mark_line(point=True, strokeWidth=2.5)
            .encode(
                x=alt.X(
                    "Thời gian:T",
                    title="Thời gian Việt Nam",
                ),
                y=alt.Y(
                    "Chỉ số AQI:Q",
                    scale=alt.Scale(domain=[0, chart_maximum]),
                ),
                color=alt.Color(
                    "Khu vực:N",
                    title="Tỉnh/thành",
                ),
                tooltip=tooltip,
            )
        )
    else:
        line = (
            alt.Chart(working)
            .mark_line(
                point=True,
                strokeWidth=3,
                color="#0f766e",
            )
            .encode(
                x=alt.X(
                    "Thời gian:T",
                    title="Thời gian Việt Nam",
                ),
                y=alt.Y(
                    "Chỉ số AQI:Q",
                    scale=alt.Scale(domain=[0, chart_maximum]),
                ),
                tooltip=tooltip,
            )
        )

    now_local = pd.Timestamp.now(tz=VIETNAM_TIMEZONE).tz_localize(None)
    now_dataframe = pd.DataFrame({"Thời gian hiện tại": [now_local]})

    now_rule = (
        alt.Chart(now_dataframe)
        .mark_rule(
            color="#475467",
            strokeDash=[6, 4],
            strokeWidth=2,
        )
        .encode(
            x="Thời gian hiện tại:T",
            tooltip=[
                alt.Tooltip(
                    "Thời gian hiện tại:T",
                    title="Hiện tại",
                    format="%d/%m/%Y %H:%M",
                )
            ],
        )
    )

    return (
        alt.layer(
            bands,
            line,
            now_rule,
        )
        .resolve_scale(
            color="independent",
        )
        .properties(height=height)
        .interactive()
    )


def build_pollutant_chart(
    dataframe: pd.DataFrame,
    pollutant_columns: list[str],
    height: int = 400,
) -> alt.Chart:
    if dataframe.empty or not pollutant_columns:
        return alt.Chart(pd.DataFrame())

    available_columns = [
        column for column in pollutant_columns if column in dataframe.columns
    ]
    if not available_columns:
        return alt.Chart(pd.DataFrame())

    working = dataframe[["forecast_time", *available_columns]].copy()
    working["Thời gian"] = to_vietnam_local_naive(working["forecast_time"])
    working = working.drop(columns=["forecast_time"])
    working = working.rename(columns=POLLUTANT_LABELS)

    melted = working.melt(
        id_vars=["Thời gian"],
        var_name="Chất ô nhiễm",
        value_name="Nồng độ",
    ).dropna()

    return (
        alt.Chart(melted)
        .mark_line(point=True, strokeWidth=2.3)
        .encode(
            x=alt.X(
                "Thời gian:T",
                title="Thời gian Việt Nam",
            ),
            y=alt.Y(
                "Nồng độ:Q",
                title="Nồng độ (µg/m³)",
            ),
            color=alt.Color(
                "Chất ô nhiễm:N",
                title="Chất ô nhiễm",
            ),
            tooltip=[
                alt.Tooltip(
                    "Thời gian:T",
                    title="Thời gian",
                    format="%d/%m/%Y %H:%M",
                ),
                alt.Tooltip(
                    "Chất ô nhiễm:N",
                    title="Thông số",
                ),
                alt.Tooltip(
                    "Nồng độ:Q",
                    title="Giá trị",
                    format=".1f",
                ),
            ],
        )
        .properties(height=height)
        .interactive()
    )


def read_query_parameter(
    name: str,
    fallback: str = "",
) -> str:
    try:
        value = st.query_params.get(name, fallback)
    except AttributeError:
        return fallback

    if isinstance(value, list):
        return clean_text(
            value[0] if value else fallback,
            fallback,
        )

    return clean_text(value, fallback)


def update_query_parameter(
    name: str,
    value: str,
) -> None:
    try:
        current = read_query_parameter(name)
        if value and current != value:
            st.query_params[name] = value
        elif not value and current:
            del st.query_params[name]
    except (AttributeError, KeyError):
        pass


def stop_with_retry(
    title: str,
    message: str,
    key: str,
) -> None:
    st.error(title)
    st.info(message)

    if st.button(
        "Thử tải lại",
        type="primary",
        key=key,
    ):
        st.cache_data.clear()
        st.rerun()

    st.stop()


# -----------------------------------------------------------------------------
# Đọc snapshot
# -----------------------------------------------------------------------------


@st.cache_data(ttl=60, show_spinner=False)
def load_health(snapshot_url: str) -> dict[str, Any]:
    return AirQualitySnapshotClient(snapshot_url).get_health()


@st.cache_data(ttl=60, show_spinner=False)
def load_latest_air_quality(
    snapshot_url: str,
) -> dict[str, Any]:
    return AirQualitySnapshotClient(snapshot_url).get_latest_air_quality(limit=5000)


@st.cache_data(ttl=60, show_spinner=False)
def load_location_summary(
    snapshot_url: str,
) -> dict[str, Any]:
    return AirQualitySnapshotClient(snapshot_url).get_location_summary(limit=1000)


@st.cache_data(ttl=60, show_spinner=False)
def load_point_history(
    snapshot_url: str,
    point_id: str,
) -> dict[str, Any]:
    return AirQualitySnapshotClient(snapshot_url).get_point_history(
        point_id=point_id,
        limit=720,
    )


@st.cache_data(ttl=60, show_spinner=False)
def load_pipeline_health(
    snapshot_url: str,
) -> dict[str, Any]:
    return AirQualitySnapshotClient(snapshot_url).get_pipeline_health()


@st.cache_data(ttl=60, show_spinner=False)
def load_data_quality(
    snapshot_url: str,
) -> dict[str, Any]:
    return AirQualitySnapshotClient(snapshot_url).get_data_quality()


@st.cache_data(ttl=60, show_spinner=False)
def load_alerts(snapshot_url: str) -> dict[str, Any]:
    return AirQualitySnapshotClient(snapshot_url).get_latest_alerts(limit=100)


def get_default_snapshot_url() -> str:
    environment_url = os.getenv(
        "PUBLIC_SNAPSHOT_BASE_URL",
        "",
    ).strip()
    if environment_url:
        return environment_url

    try:
        secret_url = st.secrets["PUBLIC_SNAPSHOT_BASE_URL"]
    except (KeyError, FileNotFoundError):
        return ""

    return str(secret_url).strip()


# -----------------------------------------------------------------------------
# Khởi tạo dữ liệu
# -----------------------------------------------------------------------------


inject_dashboard_styles()
render_dashboard_header()

snapshot_url = get_default_snapshot_url()

if not snapshot_url:
    st.warning("Website chưa được cấu hình địa chỉ dữ liệu công khai.")
    st.info(
        "Đặt `PUBLIC_SNAPSHOT_BASE_URL` trong biến môi trường hoặc Streamlit Secrets."
    )
    st.stop()

try:
    health_payload = load_health(snapshot_url)
    health_load_error = ""
except AirQualitySnapshotError as error:
    health_payload = {}
    health_load_error = str(error)

try:
    latest_payload = load_latest_air_quality(snapshot_url)
except AirQualitySnapshotError as error:
    stop_with_retry(
        "Không thể tải dữ liệu chất lượng không khí.",
        (f"Nguồn dữ liệu có thể đang tạm thời gián đoạn. Chi tiết: {error}"),
        key="retry_latest_air_quality",
    )

try:
    location_summary_payload = load_location_summary(snapshot_url)
except AirQualitySnapshotError:
    location_summary_payload = {}

records = latest_payload.get("data", [])
if not isinstance(records, list):
    stop_with_retry(
        "Dữ liệu nhận được không đúng định dạng.",
        "Website cần một danh sách bản ghi nhưng nguồn dữ liệu trả về định dạng khác.",
        key="retry_invalid_payload",
    )

air_quality_df = records_to_dataframe(records)
if air_quality_df.empty:
    stop_with_retry(
        "Hiện chưa có dữ liệu để hiển thị.",
        "Hãy thử tải lại sau khi quy trình thu thập dữ liệu hoàn thành.",
        key="retry_empty_data",
    )

health_status = clean_text(
    health_payload.get("status"),
    "UNKNOWN",
)
database_name = clean_text(
    health_payload.get("database"),
    "UNKNOWN",
)
batch_id = clean_text(
    latest_payload.get("batch_id"),
    "UNKNOWN",
)
record_count = latest_payload.get(
    "record_count",
    len(air_quality_df),
)

point_ids = sorted(
    air_quality_df["point_id"]
    .dropna()
    .astype(str)
    .str.strip()
    .loc[lambda series: series.ne("")]
    .unique()
    .tolist()
)

point_name_lookup = (
    air_quality_df[["point_id", "point_name"]]
    .dropna(subset=["point_id"])
    .drop_duplicates(
        subset=["point_id"],
        keep="first",
    )
    .set_index("point_id")["point_name"]
    .fillna("")
    .astype(str)
    .to_dict()
    if "point_name" in air_quality_df.columns
    else {}
)

point_location_lookup = (
    air_quality_df[["point_id", "location_id"]]
    .dropna(subset=["point_id"])
    .drop_duplicates(
        subset=["point_id"],
        keep="first",
    )
    .set_index("point_id")["location_id"]
    .fillna("")
    .astype(str)
    .to_dict()
    if "location_id" in air_quality_df.columns
    else {}
)


def get_point_display_name(point_id: str) -> str:
    point_name = clean_text(point_name_lookup.get(point_id))
    return point_name or point_id


nearest_forecast_df = select_nearest_forecast_records(air_quality_df)
location_summary_records = location_summary_payload.get("data", [])
if not isinstance(location_summary_records, list):
    location_summary_records = []
location_summary_df = prepare_mart_location_summary_dataframe(
    location_summary_records
)
if location_summary_df.empty:
    location_summary_df = build_location_summary_dataframe(nearest_forecast_df)

location_labels = {
    clean_text(row.location_id): clean_text(
        row.location_label,
        clean_text(row.location_id),
    )
    for row in location_summary_df[["location_id", "location_label"]].itertuples(
        index=False
    )
}

nearest_forecast_df["location_id"] = (
    nearest_forecast_df["location_id"]
    .where(
        nearest_forecast_df["location_id"].notna(),
        "",
    )
    .astype(str)
    .str.strip()
)
nearest_forecast_df["location_label"] = nearest_forecast_df["location_id"].map(
    location_labels
)

average_aqi = (
    nearest_forecast_df["us_aqi"].mean()
    if "us_aqi" in nearest_forecast_df.columns
    else float("nan")
)
maximum_aqi = (
    nearest_forecast_df["us_aqi"].max()
    if "us_aqi" in nearest_forecast_df.columns
    else float("nan")
)
latest_forecast_time = (
    nearest_forecast_df["forecast_time"].max()
    if "forecast_time" in nearest_forecast_df.columns
    else None
)
nationwide_aqi_delta = calculate_nearest_hour_delta(
    air_quality_df,
    "us_aqi",
)

data_updated_at = get_data_updated_at(
    latest_payload=latest_payload,
    health_payload=health_payload,
    dataframe=air_quality_df,
)
data_age_minutes = get_data_age_minutes(data_updated_at)

available_time_hours = calculate_available_time_hours(air_quality_df)
available_time_range_options = {
    label: hours
    for label, hours in TIME_RANGE_OPTIONS.items()
    if hours <= available_time_hours
}

if not available_time_range_options:
    available_time_range_options = {
        f"{available_time_hours} giờ hiện có": (available_time_hours)
    }

requested_hours = read_query_parameter(
    "hours",
    "24",
)
try:
    requested_hours_integer = int(requested_hours)
except ValueError:
    requested_hours_integer = 24

default_time_label = next(
    (
        label
        for label, hours in available_time_range_options.items()
        if hours == requested_hours_integer
    ),
    next(iter(available_time_range_options)),
)

toolbar_refresh, toolbar_time, toolbar_status = st.columns(
    [1, 1.2, 3],
    gap="medium",
)

with toolbar_refresh:
    refresh_requested = st.button(
        "Làm mới dữ liệu",
        type="primary",
        use_container_width=True,
    )
    if refresh_requested:
        st.cache_data.clear()
        st.rerun()

with toolbar_time:
    selected_time_label = st.selectbox(
        "Khoảng dữ liệu trên biểu đồ",
        options=list(available_time_range_options),
        index=list(available_time_range_options).index(default_time_label),
        key="global_time_range",
    )
    selected_time_hours = available_time_range_options[selected_time_label]
    update_query_parameter(
        "hours",
        str(selected_time_hours),
    )

with toolbar_status:
    updated_text = format_datetime(data_updated_at)
    relative_text = format_relative_age(data_updated_at)
    st.markdown(
        (
            '<div class="aq-toolbar-note">'
            f"<strong>Dữ liệu cập nhật:</strong> "
            f"{escape(updated_text)} · "
            f"{escape(relative_text)}"
            "<br><small>"
            f"Nguồn hiện có khoảng {available_time_hours} giờ dữ liệu. "
            "Bộ chọn bên trái chỉ thay đổi khoảng dữ liệu trên biểu đồ."
            "</small>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

if health_load_error:
    st.info(
        "Dữ liệu AQI vẫn tải được, nhưng trạng thái hệ thống "
        "đang tạm thời không truy cập được."
    )

if data_age_minutes is None:
    st.info(
        "Chưa xác định được độ mới của dữ liệu. "
        "Bạn có thể bấm Làm mới dữ liệu để kiểm tra lại."
    )
elif data_age_minutes > 120:
    st.warning(
        "Dữ liệu đã cũ hơn 2 giờ và có thể chưa phản ánh "
        "lần xử lý gần nhất của hệ thống."
    )
elif data_age_minutes > 60:
    st.warning(
        "Dữ liệu đã cũ hơn 1 giờ. Hãy thử làm mới để kiểm tra bản dữ liệu mới hơn."
    )

(
    map_tab,
    analytics_tab,
    point_tab,
    history_tab,
    alert_tab,
    operations_tab,
) = st.tabs(
    [
        "Bản đồ AQI",
        "Phân tích",
        "Điểm theo dõi",
        "Lịch sử AQI",
        "Cảnh báo",
        "Trạng thái hệ thống",
    ]
)


# -----------------------------------------------------------------------------
# Trang 1: Bản đồ
# -----------------------------------------------------------------------------


with map_tab:
    st.subheader("Bản đồ chất lượng không khí")
    st.caption(
        "Tìm tỉnh/thành hoặc bấm vào một chấm trên bản đồ để xem thông tin chi tiết."
    )
    render_aqi_legend()

    search_column, threshold_column = st.columns(
        [2, 1],
        gap="medium",
    )

    sorted_location_ids = (
        location_summary_df.sort_values("location_label")["location_id"]
        .astype(str)
        .tolist()
    )
    location_options = ["", *sorted_location_ids]

    requested_location_id = read_query_parameter("location")
    if requested_location_id not in sorted_location_ids:
        requested_location_id = ""

    with search_column:
        selected_location_search = st.selectbox(
            "Tìm tỉnh/thành",
            options=location_options,
            index=location_options.index(requested_location_id),
            format_func=lambda location_id: (
                "Toàn quốc"
                if not location_id
                else location_labels.get(
                    location_id,
                    location_id,
                )
            ),
            key="map_location_search",
        )

    with threshold_column:
        selected_threshold_label = st.selectbox(
            "Lọc theo mức AQI",
            options=list(AQI_FILTER_OPTIONS),
            key="map_aqi_threshold",
        )
        selected_threshold = AQI_FILTER_OPTIONS[selected_threshold_label]

    if selected_location_search:
        st.session_state["selected_location_id"] = selected_location_search
        update_query_parameter(
            "location",
            selected_location_search,
        )
    else:
        update_query_parameter(
            "location",
            "",
        )

    selected_location_id = st.session_state.get(
        "selected_location_id",
        "",
    )
    valid_location_ids = set(location_summary_df["location_id"].astype(str))
    if selected_location_id not in valid_location_ids:
        selected_location_id = (
            selected_location_search
            if selected_location_search in valid_location_ids
            else ""
        )

    map_data = (
        location_summary_df[
            [
                "location_id",
                "location_label",
                "latitude",
                "longitude",
                "average_us_aqi",
                "maximum_us_aqi",
                "monitoring_point_count",
                "aqi_level",
                "fill_color",
                "marker_radius",
            ]
        ]
        .dropna(subset=["latitude", "longitude"])
        .copy()
    )

    if selected_threshold is not None:
        map_data = map_data.loc[
            map_data["average_us_aqi"].fillna(-1).gt(selected_threshold)
        ].copy()

    map_data["monitoring_point_count"] = map_data["monitoring_point_count"].astype(int)

    overview_1, overview_2, overview_3, overview_4 = st.columns(4)
    overview_1.metric(
        "Tỉnh/thành đang hiển thị",
        len(map_data),
    )
    overview_2.metric(
        "Điểm theo dõi",
        len(point_ids),
    )
    overview_3.metric(
        "AQI trung bình",
        format_number(average_aqi),
        delta=format_delta(nationwide_aqi_delta),
    )
    overview_4.metric(
        "AQI cao nhất",
        format_number(maximum_aqi, 0),
    )

    if map_data.empty:
        st.warning("Không có tỉnh/thành nào phù hợp với bộ lọc AQI hiện tại.")
    else:
        if not selected_location_id:
            detail_location_id = str(location_summary_df.iloc[0]["location_id"])
        else:
            detail_location_id = selected_location_id

        detail_location_row = location_summary_df.loc[
            location_summary_df["location_id"].astype(str).eq(detail_location_id)
        ].iloc[0]

        if selected_location_id:
            map_latitude = float(detail_location_row["latitude"])
            map_longitude = float(detail_location_row["longitude"])
            map_zoom = 7.5
        else:
            map_latitude = 16.2
            map_longitude = 106.3
            map_zoom = 4.65

        map_column, detail_column = st.columns(
            [1.65, 1],
            gap="large",
        )

        with map_column:
            location_layer = pdk.Layer(
                "ScatterplotLayer",
                data=map_data,
                id="location-markers",
                get_position="[longitude, latitude]",
                get_fill_color="fill_color",
                get_line_color=[255, 255, 255, 235],
                get_radius="marker_radius",
                radius_min_pixels=8,
                radius_max_pixels=27,
                line_width_min_pixels=2,
                stroked=True,
                filled=True,
                pickable=True,
                auto_highlight=True,
                highlight_color=[15, 23, 42, 70],
            )

            selected_map_data = map_data.loc[
                map_data["location_id"].astype(str).eq(detail_location_id)
            ].copy()
            selected_layer = pdk.Layer(
                "ScatterplotLayer",
                data=selected_map_data,
                id="selected-location-marker",
                get_position="[longitude, latitude]",
                get_fill_color=[255, 255, 255, 25],
                get_line_color=[15, 118, 110, 255],
                get_radius="marker_radius",
                radius_scale=1.25,
                radius_min_pixels=13,
                radius_max_pixels=34,
                line_width_min_pixels=4,
                stroked=True,
                filled=True,
                pickable=False,
            )

            map_deck = pdk.Deck(
                map_style=CARTO_LIGHT_MAP_STYLE,
                initial_view_state=pdk.ViewState(
                    latitude=map_latitude,
                    longitude=map_longitude,
                    zoom=map_zoom,
                    pitch=0,
                    bearing=0,
                ),
                layers=[
                    location_layer,
                    selected_layer,
                ],
                tooltip={
                    "html": (
                        "<b>{location_label}</b>"
                        "<br/>AQI trung bình: {average_us_aqi}"
                        "<br/>AQI cao nhất: {maximum_us_aqi}"
                        "<br/>Mức: {aqi_level}"
                        "<br/>Điểm theo dõi: {monitoring_point_count}"
                    ),
                    "style": {
                        "backgroundColor": "#172033",
                        "color": "white",
                        "fontSize": "13px",
                    },
                },
            )

            map_event = st.pydeck_chart(
                map_deck,
                width="stretch",
                height=560,
                on_select="rerun",
                selection_mode="single-object",
                key="location_aqi_map",
            )

        selected_from_map = get_selected_location_from_map(map_event)
        if selected_from_map in valid_location_ids:
            st.session_state["selected_location_id"] = selected_from_map
            update_query_parameter(
                "location",
                selected_from_map,
            )
            detail_location_id = selected_from_map
            detail_location_row = location_summary_df.loc[
                location_summary_df["location_id"].astype(str).eq(detail_location_id)
            ].iloc[0]

        selected_points_df = (
            nearest_forecast_df.loc[
                nearest_forecast_df["location_id"].astype(str).eq(detail_location_id)
            ]
            .copy()
            .sort_values(
                by="us_aqi",
                ascending=False,
                na_position="last",
            )
        )

        with detail_column:
            st.markdown(
                "### "
                + escape(
                    clean_text(
                        detail_location_row["location_label"],
                        detail_location_id,
                    )
                )
            )
            st.caption(
                "Giá trị trung bình từ "
                f"{int(detail_location_row['monitoring_point_count'])} "
                "điểm theo dõi đại diện."
            )

            metric_1, metric_2 = st.columns(2)
            metric_1.metric(
                "AQI trung bình",
                format_number(
                    detail_location_row["average_us_aqi"],
                    1,
                ),
            )
            metric_2.metric(
                "AQI cao nhất",
                format_number(
                    detail_location_row["maximum_us_aqi"],
                    0,
                ),
            )

            aqi_level = clean_text(
                detail_location_row["aqi_level"],
                "Không có dữ liệu",
            )
            st.markdown(f"**Mức chất lượng không khí:** {aqi_level}")
            render_health_recommendation(detail_location_row["average_us_aqi"])

            pollutant_1, pollutant_2 = st.columns(2)
            pollutant_1.metric(
                "PM2.5 trung bình (µg/m³)",
                format_number(detail_location_row["average_pm2_5"]),
            )
            pollutant_2.metric(
                "PM10 trung bình (µg/m³)",
                format_number(detail_location_row["average_pm10"]),
            )

            pollutant_3, pollutant_4 = st.columns(2)
            pollutant_3.metric(
                "O₃ trung bình (µg/m³)",
                format_number(detail_location_row["average_ozone"]),
            )
            pollutant_4.metric(
                "NO₂ trung bình (µg/m³)",
                format_number(detail_location_row["average_nitrogen_dioxide"]),
            )

            worst_point_name = clean_text(detail_location_row.get("worst_point_name"))
            worst_point_id = clean_text(detail_location_row.get("worst_point_id"))
            worst_point_text = worst_point_name or get_point_display_name(
                worst_point_id
            )
            st.markdown("**Điểm có AQI cao nhất:** " + escape(worst_point_text))
            st.caption(
                "Thời điểm dữ liệu: "
                + format_datetime(detail_location_row.get("forecast_time"))
            )

        with st.expander(
            (f"Xem chi tiết {len(selected_points_df)} điểm theo dõi"),
            expanded=False,
        ):
            st.caption(
                "Các vị trí dưới đây là tọa độ lấy mẫu mô hình đại diện, "
                "không nhất thiết là trạm quan trắc vật lý."
            )

            detail_columns = [
                column
                for column in [
                    "point_id",
                    "point_name",
                    "point_type",
                    "latitude",
                    "longitude",
                    "us_aqi",
                    "pm2_5",
                    "pm10",
                    "ozone",
                    "nitrogen_dioxide",
                    "forecast_time",
                ]
                if column in selected_points_df.columns
            ]
            point_detail_df = selected_points_df[detail_columns].copy()

            if "point_type" in point_detail_df.columns:
                point_detail_df["point_type"] = point_detail_df["point_type"].apply(
                    translate_point_type
                )
            if "us_aqi" in point_detail_df.columns:
                point_detail_df["aqi_level"] = point_detail_df["us_aqi"].apply(
                    classify_aqi
                )
            if "forecast_time" in point_detail_df.columns:
                point_detail_df["forecast_time"] = point_detail_df[
                    "forecast_time"
                ].apply(format_datetime)

            point_detail_df = point_detail_df.rename(
                columns={
                    "point_id": "Mã điểm",
                    "point_name": "Tên khu vực",
                    "point_type": "Loại khu vực",
                    "latitude": "Vĩ độ",
                    "longitude": "Kinh độ",
                    "us_aqi": "Chỉ số AQI",
                    "pm2_5": "PM2.5",
                    "pm10": "PM10",
                    "ozone": "O₃",
                    "nitrogen_dioxide": "NO₂",
                    "forecast_time": "Thời điểm",
                    "aqi_level": "Mức AQI",
                }
            )
            st.dataframe(
                point_detail_df,
                width="stretch",
                hide_index=True,
            )

            st.download_button(
                "Tải danh sách điểm của tỉnh này",
                data=point_detail_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=(f"air_quality_{detail_location_id}.csv"),
                mime="text/csv",
                key=(f"download_location_{detail_location_id}"),
            )


# -----------------------------------------------------------------------------
# Trang 2: Phân tích
# -----------------------------------------------------------------------------


with analytics_tab:
    st.subheader("Phân tích và so sánh dữ liệu")
    st.caption(
        "So sánh tối đa 3 tỉnh/thành và xem xu hướng trong khoảng thời gian đã chọn."
    )

    metric_1, metric_2, metric_3 = st.columns(3)
    metric_1.metric(
        "Số điểm theo dõi",
        len(point_ids),
    )
    metric_2.metric(
        "Tổng số bản ghi",
        record_count,
    )
    metric_3.metric(
        "AQI trung bình gần nhất",
        format_number(average_aqi, 1),
        delta=format_delta(nationwide_aqi_delta),
    )

    ranking_column, distribution_column = st.columns(
        2,
        gap="large",
    )

    with ranking_column:
        st.markdown("#### Tỉnh/thành có AQI cao")
        ranking_df = (
            location_summary_df[
                [
                    "location_label",
                    "average_us_aqi",
                ]
            ]
            .dropna(subset=["average_us_aqi"])
            .head(15)
            .rename(
                columns={
                    "location_label": "Tỉnh/thành",
                    "average_us_aqi": "AQI trung bình",
                }
            )
        )

        ranking_chart = (
            alt.Chart(ranking_df)
            .mark_bar(
                color="#0f766e",
                cornerRadiusEnd=4,
            )
            .encode(
                x=alt.X(
                    "AQI trung bình:Q",
                    title="AQI trung bình",
                ),
                y=alt.Y(
                    "Tỉnh/thành:N",
                    sort="-x",
                    title=None,
                ),
                tooltip=[
                    alt.Tooltip(
                        "Tỉnh/thành:N",
                        title="Tỉnh/thành",
                    ),
                    alt.Tooltip(
                        "AQI trung bình:Q",
                        format=".1f",
                    ),
                ],
            )
            .properties(height=380)
        )
        st.altair_chart(
            ranking_chart,
            use_container_width=True,
        )

    with distribution_column:
        st.markdown("#### Phân bố mức chất lượng không khí")
        distribution_series = (
            location_summary_df["aqi_level"]
            .value_counts()
            .reindex(
                AQI_ORDER,
                fill_value=0,
            )
        )
        distribution_df = (
            distribution_series.loc[lambda series: series.gt(0)]
            .rename_axis("Mức AQI")
            .reset_index(name="Số tỉnh/thành")
        )

        distribution_chart = (
            alt.Chart(distribution_df)
            .mark_bar(cornerRadiusEnd=4)
            .encode(
                x=alt.X(
                    "Số tỉnh/thành:Q",
                    title="Số tỉnh/thành",
                ),
                y=alt.Y(
                    "Mức AQI:N",
                    sort=AQI_ORDER,
                    title=None,
                ),
                color=alt.Color(
                    "Mức AQI:N",
                    scale=alt.Scale(
                        domain=AQI_BANDS["Mức AQI"].tolist(),
                        range=AQI_BANDS["Màu"].tolist(),
                    ),
                    legend=None,
                ),
                tooltip=[
                    "Mức AQI:N",
                    "Số tỉnh/thành:Q",
                ],
            )
            .properties(height=380)
        )
        st.altair_chart(
            distribution_chart,
            use_container_width=True,
        )

    st.markdown("#### So sánh tỉnh/thành")

    sorted_location_labels = sorted(
        {
            clean_text(
                label,
                location_id,
            )
            for location_id, label in location_labels.items()
        }
    )

    selected_comparison_locations = st.multiselect(
        "Chọn tối đa 3 tỉnh/thành",
        options=sorted_location_labels,
        default=[],
        max_selections=3,
        placeholder=("Để trống để xem trung bình toàn quốc"),
        key="comparison_locations",
    )

    comparison_df = filter_by_time_range(
        air_quality_df,
        selected_time_hours,
    )

    comparison_df["location_id"] = (
        comparison_df["location_id"]
        .where(
            comparison_df["location_id"].notna(),
            "",
        )
        .astype(str)
        .str.strip()
    )

    comparison_df["location_label"] = comparison_df["location_id"].map(location_labels)

    if "location_name" in comparison_df.columns:
        comparison_df["location_label"] = comparison_df["location_label"].where(
            comparison_df["location_label"].notna(),
            comparison_df["location_name"],
        )

    comparison_df["location_label"] = (
        comparison_df["location_label"]
        .where(
            comparison_df["location_label"].notna(),
            comparison_df["location_id"],
        )
        .astype(str)
        .str.strip()
    )

    if selected_comparison_locations:
        comparison_df = comparison_df.loc[
            comparison_df["location_label"].isin(selected_comparison_locations)
        ].copy()

    valid_comparison_df = comparison_df.dropna(
        subset=["forecast_time", "us_aqi"]
    ).copy()

    if valid_comparison_df.empty:
        st.info(
            "Không tìm thấy dữ liệu AQI cho các tỉnh/thành "
            "đang chọn trong khoảng thời gian hiện có."
        )

        available_labels = sorted(
            comparison_df["location_label"]
            .dropna()
            .astype(str)
            .loc[lambda series: series.str.strip().ne("")]
            .unique()
            .tolist()
        )
        if available_labels:
            st.caption("Các tỉnh/thành đang có dữ liệu: " + ", ".join(available_labels))
    else:
        comparison_series_column = (
            "location_label" if selected_comparison_locations else None
        )
        aqi_comparison_chart = build_aqi_chart(
            valid_comparison_df,
            series_column=comparison_series_column,
        )
        st.altair_chart(
            aqi_comparison_chart,
            use_container_width=True,
        )

        displayed_locations = (
            valid_comparison_df["location_id"].astype(str).nunique()
            if "location_id" in valid_comparison_df.columns
            else 0
        )
        displayed_times = valid_comparison_df["forecast_time"].nunique()
        st.caption(
            f"Biểu đồ đang dùng {len(valid_comparison_df):,} bản ghi, "
            f"{displayed_locations} tỉnh/thành và "
            f"{displayed_times} thời điểm."
        )

    st.caption(
        "Vùng màu thể hiện các mức AQI. Đường nét đứt "
        "đánh dấu thời điểm hiện tại; phần bên phải chủ yếu là dự báo."
    )

    st.markdown("#### Bộ lọc dữ liệu chi tiết")
    filter_1, filter_2 = st.columns(2)

    with filter_1:
        selected_analytics_location = st.selectbox(
            "Tỉnh/thành",
            options=["", *sorted_location_ids],
            format_func=lambda location_id: (
                "Tất cả tỉnh/thành"
                if not location_id
                else location_labels.get(
                    location_id,
                    location_id,
                )
            ),
            key="analytics_location_filter",
        )

    analytics_df = filter_by_time_range(
        air_quality_df,
        selected_time_hours,
    )
    if selected_analytics_location:
        analytics_df = analytics_df.loc[
            analytics_df["location_id"].astype(str).eq(selected_analytics_location)
        ].copy()

    available_points = sorted(
        analytics_df["point_id"].dropna().astype(str).unique().tolist()
    )

    with filter_2:
        selected_points = st.multiselect(
            "Điểm theo dõi",
            options=available_points,
            default=[],
            format_func=get_point_display_name,
            placeholder=("Để trống để xem toàn bộ"),
            key="analytics_point_filter",
        )

    if selected_points:
        analytics_df = analytics_df.loc[
            analytics_df["point_id"].astype(str).isin(selected_points)
        ].copy()

    available_metrics = [
        column
        for column in [
            "pm2_5",
            "pm10",
            "ozone",
            "nitrogen_dioxide",
            "sulphur_dioxide",
        ]
        if column in analytics_df.columns
    ]

    selected_pollutants = st.multiselect(
        "Chọn chất ô nhiễm để vẽ biểu đồ",
        options=available_metrics,
        default=[
            column
            for column in [
                "pm2_5",
                "pm10",
            ]
            if column in available_metrics
        ],
        format_func=lambda column: POLLUTANT_LABELS.get(
            column,
            column,
        ),
        key="analytics_pollutants",
    )

    if selected_pollutants and not analytics_df.empty:
        st.altair_chart(
            build_pollutant_chart(
                analytics_df,
                selected_pollutants,
            ),
            use_container_width=True,
        )
    else:
        st.info("Chọn ít nhất một chất ô nhiễm để hiển thị biểu đồ.")

    st.markdown("#### Dữ liệu đã lọc")
    st.caption(
        "Bảng dưới đây giữ tên cột kỹ thuật để phục vụ "
        "việc kiểm tra dữ liệu và nguồn gốc lần xử lý."
    )

    technical_columns = [
        column
        for column in [
            "forecast_time",
            "location_id",
            "location_name",
            "point_id",
            "point_name",
            "point_type",
            "latitude",
            "longitude",
            "pm2_5",
            "pm10",
            "ozone",
            "nitrogen_dioxide",
            "sulphur_dioxide",
            "carbon_monoxide",
            "us_aqi",
            "source",
            "batch_id",
            "schema_version",
            "ingested_at",
        ]
        if column in analytics_df.columns
    ]

    technical_df = analytics_df[technical_columns].copy()
    if "forecast_time" in technical_df.columns:
        technical_df = technical_df.sort_values("forecast_time")

    st.dataframe(
        technical_df,
        width="stretch",
        hide_index=True,
    )
    st.download_button(
        "Tải dữ liệu đã lọc",
        data=technical_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="air_quality_filtered.csv",
        mime="text/csv",
        key="download_analytics",
    )


# -----------------------------------------------------------------------------
# Trang 3: Điểm theo dõi
# -----------------------------------------------------------------------------


with point_tab:
    st.subheader("Chi tiết điểm theo dõi")
    st.caption("Tìm một vị trí đại diện để xem chỉ số gần nhất và xu hướng theo giờ.")

    requested_point_id = read_query_parameter("point")
    if requested_point_id not in point_ids:
        requested_point_id = point_ids[0] if point_ids else ""

    selected_point_id = st.selectbox(
        "Tìm điểm theo dõi",
        options=point_ids,
        index=(
            point_ids.index(requested_point_id)
            if requested_point_id in point_ids
            else 0
        ),
        format_func=get_point_display_name,
        key="point_search",
    )
    update_query_parameter(
        "point",
        selected_point_id,
    )

    try:
        point_payload = load_point_history(
            snapshot_url,
            selected_point_id,
        )
        point_df = records_to_dataframe(point_payload.get("data", []))
    except AirQualitySnapshotError as error:
        st.error("Không thể tải dữ liệu cho điểm theo dõi này.")
        st.info(str(error))
        if st.button(
            "Thử tải lại điểm này",
            key="retry_point_history",
        ):
            load_point_history.clear()
            st.rerun()
        point_df = pd.DataFrame()

    point_df = filter_by_time_range(
        point_df,
        selected_time_hours,
    )

    if point_df.empty:
        st.info("Điểm theo dõi này chưa có dữ liệu trong khoảng thời gian đã chọn.")
    else:
        point_df = point_df.sort_values("forecast_time")
        nearest_point_df = select_nearest_forecast_records(point_df)
        first_record = (
            nearest_point_df.iloc[0] if not nearest_point_df.empty else point_df.iloc[0]
        )

        selected_point_name = clean_text(
            first_record.get("point_name"),
            get_point_display_name(selected_point_id),
        )
        selected_location_id = clean_text(
            first_record.get("location_id"),
            clean_text(point_location_lookup.get(selected_point_id)),
        )
        selected_location_name = clean_text(
            first_record.get("location_name"),
            location_labels.get(
                selected_location_id,
                selected_location_id,
            ),
        )
        selected_point_type = translate_point_type(first_record.get("point_type"))

        st.markdown(f"### {escape(selected_point_name)}")
        detail_parts = [
            part
            for part in [
                selected_location_name,
                selected_point_type,
            ]
            if part
        ]
        if detail_parts:
            st.caption(" · ".join(detail_parts))

        latitude = first_record.get("latitude")
        longitude = first_record.get("longitude")
        if (
            latitude is not None
            and longitude is not None
            and not pd.isna(latitude)
            and not pd.isna(longitude)
        ):
            st.caption(
                f"Tọa độ đại diện: {float(latitude):.5f}, {float(longitude):.5f}"
            )

        current_aqi = first_record.get("us_aqi")
        point_aqi_delta = calculate_nearest_hour_delta(
            point_df,
            "us_aqi",
        )

        metric_1, metric_2, metric_3 = st.columns(3)
        metric_1.metric(
            "PM2.5 gần nhất (µg/m³)",
            format_number(first_record.get("pm2_5")),
        )
        metric_2.metric(
            "PM10 gần nhất (µg/m³)",
            format_number(first_record.get("pm10")),
        )
        metric_3.metric(
            "AQI gần nhất",
            format_number(
                current_aqi,
                0,
            ),
            delta=format_delta(point_aqi_delta),
        )

        current_level = classify_aqi(current_aqi)
        st.markdown(f"**Mức chất lượng không khí gần nhất:** {current_level}")
        render_health_recommendation(current_aqi)

        if "us_aqi" in point_df.columns:
            st.markdown("#### Xu hướng chỉ số AQI")
            st.altair_chart(
                build_aqi_chart(point_df),
                use_container_width=True,
            )
            st.caption(
                "Vùng màu thể hiện mức AQI và đường nét đứt "
                "đánh dấu thời điểm hiện tại."
            )

        pollutant_columns = [
            column
            for column in [
                "pm2_5",
                "pm10",
                "ozone",
                "nitrogen_dioxide",
                "sulphur_dioxide",
            ]
            if column in point_df.columns
        ]

        if pollutant_columns:
            st.markdown("#### Xu hướng các chất ô nhiễm")
            st.altair_chart(
                build_pollutant_chart(
                    point_df,
                    pollutant_columns,
                ),
                use_container_width=True,
            )

        point_display_columns = [
            column
            for column in [
                "forecast_time",
                "pm2_5",
                "pm10",
                "ozone",
                "nitrogen_dioxide",
                "sulphur_dioxide",
                "carbon_monoxide",
                "us_aqi",
            ]
            if column in point_df.columns
        ]
        point_display_df = point_df[point_display_columns].copy()
        if "forecast_time" in point_display_df.columns:
            point_display_df["forecast_time"] = point_display_df["forecast_time"].apply(
                format_datetime
            )

        point_display_df = point_display_df.rename(
            columns={
                "forecast_time": "Thời điểm",
                **POLLUTANT_LABELS,
            }
        )

        st.dataframe(
            point_display_df,
            width="stretch",
            hide_index=True,
        )
        st.download_button(
            "Tải dữ liệu của điểm này",
            data=point_display_df.to_csv(index=False).encode("utf-8-sig"),
            file_name=(f"air_quality_{selected_point_id}.csv"),
            mime="text/csv",
            key="download_point",
        )


# -----------------------------------------------------------------------------
# Trang 4: Lịch sử AQI
# -----------------------------------------------------------------------------


with history_tab:
    st.subheader("Lịch sử chất lượng không khí")
    st.caption(
        "Chọn tỉnh/thành, điểm theo dõi và khoảng ngày "
        "để xem lại AQI đã được hệ thống lưu trước đó."
    )

    history_location_ids = sorted(
        {
            clean_text(location_id)
            for location_id in point_location_lookup.values()
            if clean_text(location_id)
        },
        key=lambda location_id: location_labels.get(
            location_id,
            location_id,
        ),
    )

    if not history_location_ids:
        st.info("Chưa có thông tin tỉnh/thành cho dữ liệu lịch sử.")
    else:
        requested_history_location = read_query_parameter("history_location")
        if requested_history_location not in history_location_ids:
            requested_history_location = history_location_ids[0]

        history_filter_1, history_filter_2 = st.columns(
            2,
            gap="medium",
        )

        with history_filter_1:
            selected_history_location = st.selectbox(
                "Tỉnh/thành",
                options=history_location_ids,
                index=history_location_ids.index(requested_history_location),
                format_func=lambda location_id: location_labels.get(
                    location_id,
                    location_id,
                ),
                key="history_location_filter",
            )

        update_query_parameter(
            "history_location",
            selected_history_location,
        )

        history_point_ids = sorted(
            [
                point_id
                for point_id in point_ids
                if clean_text(point_location_lookup.get(point_id))
                == selected_history_location
            ],
            key=get_point_display_name,
        )

        with history_filter_2:
            requested_history_point = read_query_parameter("history_point")
            if requested_history_point not in history_point_ids:
                requested_history_point = (
                    history_point_ids[0] if history_point_ids else ""
                )

            selected_history_point = (
                st.selectbox(
                    "Điểm theo dõi",
                    options=history_point_ids,
                    index=(
                        history_point_ids.index(requested_history_point)
                        if requested_history_point in history_point_ids
                        else 0
                    ),
                    format_func=(get_point_display_name),
                    key="history_point_filter",
                )
                if history_point_ids
                else ""
            )

        update_query_parameter(
            "history_point",
            selected_history_point,
        )

        if not selected_history_point:
            st.info("Tỉnh/thành này chưa có điểm theo dõi.")
        else:
            try:
                history_payload = load_point_history(
                    snapshot_url,
                    selected_history_point,
                )
                history_df = records_to_dataframe(
                    history_payload.get(
                        "data",
                        [],
                    )
                )
            except AirQualitySnapshotError as error:
                st.error("Không thể tải dữ liệu lịch sử cho điểm này.")
                st.info(str(error))
                if st.button(
                    "Thử tải lại lịch sử",
                    key="retry_history_page",
                ):
                    load_point_history.clear()
                    st.rerun()

                history_df = pd.DataFrame()

            required_history_columns = {
                "forecast_time",
                "us_aqi",
            }

            if history_df.empty or not required_history_columns.issubset(
                history_df.columns
            ):
                st.info("Điểm theo dõi này chưa có dữ liệu lịch sử phù hợp.")
            else:
                history_df = (
                    history_df.dropna(subset=["forecast_time"])
                    .sort_values("forecast_time")
                    .copy()
                )

                history_df["_forecast_time_vn"] = history_df[
                    "forecast_time"
                ].dt.tz_convert(VIETNAM_TIMEZONE)
                history_df["_history_date"] = history_df["_forecast_time_vn"].dt.date

                include_current_forecast = st.checkbox(
                    ("Bao gồm hôm nay và dữ liệu dự báo"),
                    value=False,
                    help=("Mặc định trang chỉ hiển thị các ngày đã kết thúc."),
                    key=("history_include_current_forecast"),
                )

                today_vn = pd.Timestamp.now(tz=VIETNAM_TIMEZONE).date()

                if not include_current_forecast:
                    history_df = history_df.loc[
                        history_df["_history_date"] < today_vn
                    ].copy()

                if history_df.empty:
                    st.info("Chưa có ngày lịch sử phù hợp với bộ lọc này.")
                else:
                    minimum_history_date = history_df["_history_date"].min()
                    maximum_history_date = history_df["_history_date"].max()
                    default_start_date = max(
                        minimum_history_date,
                        (
                            pd.Timestamp(maximum_history_date) - pd.Timedelta(days=6)
                        ).date(),
                    )

                    date_filter_1, date_filter_2 = st.columns(
                        2,
                        gap="medium",
                    )

                    with date_filter_1:
                        selected_start_date = st.date_input(
                            "Từ ngày",
                            value=(default_start_date),
                            min_value=(minimum_history_date),
                            max_value=(maximum_history_date),
                            format="DD/MM/YYYY",
                            key=(f"history_start_{selected_history_point}"),
                        )

                    with date_filter_2:
                        selected_end_date = st.date_input(
                            "Đến ngày",
                            value=(maximum_history_date),
                            min_value=(minimum_history_date),
                            max_value=(maximum_history_date),
                            format="DD/MM/YYYY",
                            key=(f"history_end_{selected_history_point}"),
                        )

                    if selected_start_date > selected_end_date:
                        st.error("Ngày bắt đầu không được lớn hơn ngày kết thúc.")
                    else:
                        filtered_history_df = history_df.loc[
                            history_df["_history_date"].between(
                                selected_start_date,
                                selected_end_date,
                                inclusive="both",
                            )
                        ].copy()

                        if filtered_history_df.empty:
                            st.info("Không có dữ liệu trong khoảng ngày đã chọn.")
                        else:
                            for column in [
                                "us_aqi",
                                "pm2_5",
                                "pm10",
                                "ozone",
                                "nitrogen_dioxide",
                            ]:
                                if column not in filtered_history_df.columns:
                                    filtered_history_df[column] = pd.NA

                            valid_aqi = pd.to_numeric(
                                filtered_history_df["us_aqi"],
                                errors="coerce",
                            ).dropna()

                            average_history_aqi = (
                                valid_aqi.mean() if not valid_aqi.empty else pd.NA
                            )
                            minimum_history_aqi = (
                                valid_aqi.min() if not valid_aqi.empty else pd.NA
                            )
                            maximum_history_aqi = (
                                valid_aqi.max() if not valid_aqi.empty else pd.NA
                            )

                            worst_time_text = "N/A"
                            if not valid_aqi.empty:
                                worst_index = pd.to_numeric(
                                    filtered_history_df["us_aqi"],
                                    errors="coerce",
                                ).idxmax()
                                worst_time_text = format_datetime(
                                    filtered_history_df.loc[
                                        worst_index,
                                        "forecast_time",
                                    ]
                                )

                            (
                                history_metric_1,
                                history_metric_2,
                                history_metric_3,
                                history_metric_4,
                            ) = st.columns(4)

                            history_metric_1.metric(
                                "Số ngày có dữ liệu",
                                filtered_history_df["_history_date"].nunique(),
                            )
                            history_metric_2.metric(
                                "AQI trung bình",
                                format_number(
                                    average_history_aqi,
                                    1,
                                ),
                            )
                            history_metric_3.metric(
                                "AQI thấp nhất",
                                format_number(
                                    minimum_history_aqi,
                                    0,
                                ),
                            )
                            history_metric_4.metric(
                                "AQI cao nhất",
                                format_number(
                                    maximum_history_aqi,
                                    0,
                                ),
                            )

                            st.caption(
                                "Thời điểm AQI cao nhất: "
                                f"{worst_time_text} · "
                                f"{len(filtered_history_df):,} "
                                "bản ghi theo giờ."
                            )

                            render_aqi_legend()

                            history_view_mode = st.radio(
                                "Kiểu hiển thị AQI",
                                options=[
                                    "Theo giờ",
                                    "Theo ngày",
                                ],
                                horizontal=True,
                                key=(f"history_view_{selected_history_point}"),
                            )

                            daily_summary_df = (
                                filtered_history_df.groupby(
                                    "_history_date",
                                    as_index=False,
                                )
                                .agg(
                                    average_us_aqi=(
                                        "us_aqi",
                                        "mean",
                                    ),
                                    minimum_us_aqi=(
                                        "us_aqi",
                                        "min",
                                    ),
                                    maximum_us_aqi=(
                                        "us_aqi",
                                        "max",
                                    ),
                                    available_hours=(
                                        "forecast_time",
                                        "nunique",
                                    ),
                                    average_pm2_5=(
                                        "pm2_5",
                                        "mean",
                                    ),
                                    maximum_pm2_5=(
                                        "pm2_5",
                                        "max",
                                    ),
                                    average_pm10=(
                                        "pm10",
                                        "mean",
                                    ),
                                    maximum_pm10=(
                                        "pm10",
                                        "max",
                                    ),
                                    average_ozone=(
                                        "ozone",
                                        "mean",
                                    ),
                                    maximum_ozone=(
                                        "ozone",
                                        "max",
                                    ),
                                )
                                .sort_values("_history_date")
                            )

                            numeric_daily_columns = [
                                column
                                for column in (daily_summary_df.columns)
                                if column != "_history_date"
                            ]
                            daily_summary_df[numeric_daily_columns] = daily_summary_df[
                                numeric_daily_columns
                            ].round(1)

                            if history_view_mode == "Theo giờ":
                                st.markdown("#### Diễn biến AQI theo giờ")
                                st.altair_chart(
                                    build_aqi_chart(
                                        filtered_history_df,
                                        height=460,
                                    ),
                                    use_container_width=True,
                                )
                            else:
                                st.markdown("#### Tổng hợp AQI theo ngày")
                                daily_chart_df = (
                                    daily_summary_df[
                                        [
                                            "_history_date",
                                            "average_us_aqi",
                                            "maximum_us_aqi",
                                        ]
                                    ]
                                    .rename(
                                        columns={
                                            "_history_date": ("Ngày"),
                                            "average_us_aqi": ("AQI trung bình"),
                                            "maximum_us_aqi": ("AQI cao nhất"),
                                        }
                                    )
                                    .melt(
                                        id_vars=["Ngày"],
                                        var_name=("Loại chỉ số"),
                                        value_name="AQI",
                                    )
                                )

                                daily_chart = (
                                    alt.Chart(daily_chart_df)
                                    .mark_line(
                                        point=True,
                                        strokeWidth=3,
                                    )
                                    .encode(
                                        x=alt.X(
                                            "Ngày:T",
                                            title="Ngày",
                                        ),
                                        y=alt.Y(
                                            "AQI:Q",
                                            title=("Chỉ số AQI"),
                                        ),
                                        color=alt.Color(
                                            "Loại chỉ số:N",
                                            title=None,
                                        ),
                                        tooltip=[
                                            alt.Tooltip(
                                                "Ngày:T",
                                                title="Ngày",
                                                format=("%d/%m/%Y"),
                                            ),
                                            alt.Tooltip(
                                                ("Loại chỉ số:N"),
                                                title=("Chỉ số"),
                                            ),
                                            alt.Tooltip(
                                                "AQI:Q",
                                                format=".1f",
                                            ),
                                        ],
                                    )
                                    .properties(height=440)
                                    .interactive()
                                )
                                st.altair_chart(
                                    daily_chart,
                                    use_container_width=True,
                                )

                            pollutant_columns = [
                                column
                                for column in [
                                    "pm2_5",
                                    "pm10",
                                    "ozone",
                                    "nitrogen_dioxide",
                                ]
                                if column in filtered_history_df.columns
                            ]

                            if pollutant_columns:
                                st.markdown("#### Diễn biến các chất ô nhiễm")
                                st.altair_chart(
                                    build_pollutant_chart(
                                        filtered_history_df,
                                        pollutant_columns,
                                        height=420,
                                    ),
                                    use_container_width=True,
                                )

                            st.markdown("#### Bảng tổng hợp theo ngày")

                            daily_display_df = daily_summary_df.rename(
                                columns={
                                    "_history_date": "Ngày",
                                    "average_us_aqi": ("AQI trung bình"),
                                    "minimum_us_aqi": ("AQI thấp nhất"),
                                    "maximum_us_aqi": ("AQI cao nhất"),
                                    "available_hours": ("Số giờ có dữ liệu"),
                                    "average_pm2_5": ("PM2.5 trung bình"),
                                    "maximum_pm2_5": ("PM2.5 cao nhất"),
                                    "average_pm10": ("PM10 trung bình"),
                                    "maximum_pm10": ("PM10 cao nhất"),
                                    "average_ozone": ("O₃ trung bình"),
                                    "maximum_ozone": ("O₃ cao nhất"),
                                }
                            )
                            daily_display_df["Ngày"] = daily_display_df["Ngày"].apply(
                                lambda value: pd.Timestamp(value).strftime("%d/%m/%Y")
                            )

                            st.dataframe(
                                daily_display_df,
                                width="stretch",
                                hide_index=True,
                            )

                            history_download_df = filtered_history_df[
                                [
                                    column
                                    for column in [
                                        "forecast_time",
                                        "location_id",
                                        "location_name",
                                        "point_id",
                                        "point_name",
                                        "pm2_5",
                                        "pm10",
                                        "ozone",
                                        "nitrogen_dioxide",
                                        "sulphur_dioxide",
                                        "carbon_monoxide",
                                        "us_aqi",
                                        "source",
                                        "batch_id",
                                    ]
                                    if column in filtered_history_df.columns
                                ]
                            ].copy()
                            if "forecast_time" in history_download_df.columns:
                                history_download_df["forecast_time"] = (
                                    history_download_df["forecast_time"].apply(
                                        format_datetime
                                    )
                                )

                            download_1, download_2 = st.columns(2)
                            with download_1:
                                st.download_button(
                                    ("Tải dữ liệu theo giờ"),
                                    data=(
                                        history_download_df.to_csv(index=False).encode(
                                            "utf-8-sig"
                                        )
                                    ),
                                    file_name=(
                                        "aqi_history_hourly_"
                                        f"{selected_history_point}_"
                                        f"{selected_start_date}_"
                                        f"{selected_end_date}.csv"
                                    ),
                                    mime="text/csv",
                                    use_container_width=True,
                                    key=("download_history_hourly"),
                                )

                            with download_2:
                                st.download_button(
                                    ("Tải tổng hợp theo ngày"),
                                    data=(
                                        daily_display_df.to_csv(index=False).encode(
                                            "utf-8-sig"
                                        )
                                    ),
                                    file_name=(
                                        "aqi_history_daily_"
                                        f"{selected_history_point}_"
                                        f"{selected_start_date}_"
                                        f"{selected_end_date}.csv"
                                    ),
                                    mime="text/csv",
                                    use_container_width=True,
                                    key=("download_history_daily"),
                                )

                            st.caption(
                                "Dữ liệu lịch sử là "
                                "dữ liệu mô hình Open-Meteo "
                                "đã được pipeline lưu tại "
                                "thời điểm trước đó, không "
                                "phải số đo chính thức từ "
                                "trạm quan trắc."
                            )


# -----------------------------------------------------------------------------
# Trang 5: Cảnh báo
# -----------------------------------------------------------------------------


with alert_tab:
    st.subheader("Cảnh báo chất lượng không khí")
    st.caption(
        "Theo dõi các điểm có AQI vượt ngưỡng và lọc "
        "theo mức độ, tỉnh/thành hoặc trạng thái."
    )

    try:
        alert_payload = load_alerts(snapshot_url)
        alert_df = records_to_dataframe(alert_payload.get("data", []))
    except AirQualitySnapshotError as error:
        st.warning("Dữ liệu cảnh báo đang tạm thời không truy cập được.")
        st.caption(str(error))
        if st.button(
            "Thử tải lại cảnh báo",
            key="retry_alerts",
        ):
            load_alerts.clear()
            st.rerun()
        alert_df = pd.DataFrame()

    if alert_df.empty:
        st.info("Không có cảnh báo trong bản dữ liệu hiện tại.")
    else:
        if "point_id" in alert_df.columns:
            alert_df["point_name"] = (
                alert_df["point_id"].astype(str).map(point_name_lookup)
            )
            alert_df["point_name"] = alert_df.apply(
                lambda row: clean_text(
                    row.get("point_name"),
                    get_point_display_name(clean_text(row.get("point_id"))),
                ),
                axis=1,
            )

        if "location_id" in alert_df.columns:
            alert_df["location_label"] = (
                alert_df["location_id"].astype(str).map(location_labels)
            )
            alert_df["location_label"] = alert_df.apply(
                lambda row: clean_text(
                    row.get("location_label"),
                    clean_text(
                        row.get("location_id"),
                        "Không rõ",
                    ),
                ),
                axis=1,
            )

        total_alerts = len(alert_df)
        critical_alerts = (
            int(alert_df["severity"].astype(str).str.upper().eq("CRITICAL").sum())
            if "severity" in alert_df.columns
            else 0
        )
        high_alerts = (
            int(alert_df["severity"].astype(str).str.upper().eq("HIGH").sum())
            if "severity" in alert_df.columns
            else 0
        )
        open_alerts = (
            int(alert_df["status"].astype(str).str.upper().eq("OPEN").sum())
            if "status" in alert_df.columns
            else total_alerts
        )

        alert_metric_1, alert_metric_2, alert_metric_3, alert_metric_4 = st.columns(4)
        alert_metric_1.metric(
            "Tổng cảnh báo",
            total_alerts,
        )
        alert_metric_2.metric(
            "Nghiêm trọng",
            critical_alerts,
        )
        alert_metric_3.metric(
            "Mức cao",
            high_alerts,
        )
        alert_metric_4.metric(
            "Đang mở",
            open_alerts,
        )

        filter_1, filter_2, filter_3 = st.columns(3)

        with filter_1:
            severity_values = (
                sorted(
                    alert_df["severity"]
                    .dropna()
                    .astype(str)
                    .str.upper()
                    .unique()
                    .tolist()
                )
                if "severity" in alert_df.columns
                else []
            )
            selected_severities = st.multiselect(
                "Mức cảnh báo",
                options=severity_values,
                default=severity_values,
                format_func=translate_alert_severity,
                key="alert_severity_filter",
            )

        with filter_2:
            alert_location_values = (
                sorted(
                    alert_df["location_label"].dropna().astype(str).unique().tolist()
                )
                if "location_label" in alert_df.columns
                else []
            )
            selected_alert_location = st.selectbox(
                "Tỉnh/thành",
                options=[
                    "Tất cả tỉnh/thành",
                    *alert_location_values,
                ],
                key="alert_location_filter",
            )

        with filter_3:
            alert_status_values = (
                sorted(
                    alert_df["status"]
                    .dropna()
                    .astype(str)
                    .str.upper()
                    .unique()
                    .tolist()
                )
                if "status" in alert_df.columns
                else []
            )
            selected_alert_status = st.selectbox(
                "Trạng thái",
                options=[
                    "Tất cả trạng thái",
                    *alert_status_values,
                ],
                format_func=lambda value: (
                    value if value.startswith("Tất cả") else translate_status(value)
                ),
                key="alert_status_filter",
            )

        filtered_alert_df = alert_df.copy()

        if severity_values and selected_severities:
            filtered_alert_df = filtered_alert_df.loc[
                filtered_alert_df["severity"]
                .astype(str)
                .str.upper()
                .isin(selected_severities)
            ].copy()
        elif severity_values:
            filtered_alert_df = filtered_alert_df.iloc[0:0].copy()

        if selected_alert_location != "Tất cả tỉnh/thành":
            filtered_alert_df = filtered_alert_df.loc[
                filtered_alert_df["location_label"].eq(selected_alert_location)
            ].copy()

        if (
            selected_alert_status != "Tất cả trạng thái"
            and "status" in filtered_alert_df.columns
        ):
            filtered_alert_df = filtered_alert_df.loc[
                filtered_alert_df["status"]
                .astype(str)
                .str.upper()
                .eq(selected_alert_status)
            ].copy()

        st.markdown("#### Danh sách cảnh báo")

        alert_display_columns = [
            column
            for column in [
                "alert_time",
                "location_label",
                "point_name",
                "aqi_value",
                "aqi_level",
                "severity",
                "status",
                "message",
            ]
            if column in filtered_alert_df.columns
        ]
        alert_display_df = filtered_alert_df[alert_display_columns].copy()

        if "alert_time" in alert_display_df.columns:
            alert_display_df["alert_time"] = alert_display_df["alert_time"].apply(
                format_datetime
            )
        if "severity" in alert_display_df.columns:
            alert_display_df["severity"] = alert_display_df["severity"].apply(
                translate_alert_severity
            )
        if "status" in alert_display_df.columns:
            alert_display_df["status"] = alert_display_df["status"].apply(
                translate_status
            )

        alert_display_df = alert_display_df.rename(
            columns={
                "alert_time": "Thời điểm",
                "location_label": "Tỉnh/thành",
                "point_name": "Điểm theo dõi",
                "aqi_value": "Chỉ số AQI",
                "aqi_level": "Mức AQI",
                "severity": "Mức cảnh báo",
                "status": "Trạng thái",
                "message": "Nội dung",
            }
        )

        if alert_display_df.empty:
            st.info("Không có cảnh báo phù hợp với bộ lọc hiện tại.")
        else:
            st.dataframe(
                alert_display_df,
                width="stretch",
                hide_index=True,
            )
            st.download_button(
                "Tải danh sách cảnh báo",
                data=alert_display_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="air_quality_alerts.csv",
                mime="text/csv",
                key="download_alerts",
            )


# -----------------------------------------------------------------------------
# Trang 6: Trạng thái hệ thống
# -----------------------------------------------------------------------------


with operations_tab:
    st.subheader("Trạng thái hoạt động của hệ thống")
    st.caption(
        "Theo dõi các bước xử lý, số lượng dữ liệu và kết quả kiểm tra chất lượng."
    )

    try:
        pipeline_payload = load_pipeline_health(snapshot_url)
        pipeline_df = records_to_dataframe(pipeline_payload.get("data", []))
        pipeline_status = clean_text(
            pipeline_payload.get("status"),
            "UNKNOWN",
        )
        pipeline_batch_id = clean_text(
            pipeline_payload.get("batch_id"),
            "UNKNOWN",
        )
    except AirQualitySnapshotError as error:
        st.warning("Trạng thái quy trình xử lý đang tạm thời không truy cập được.")
        st.caption(str(error))
        pipeline_payload = {}
        pipeline_df = pd.DataFrame()
        pipeline_status = "UNKNOWN"
        pipeline_batch_id = "UNKNOWN"

    failed_stage_count = (
        int((~pipeline_df["status"].astype(str).str.upper().eq("SUCCESS")).sum())
        if ("status" in pipeline_df.columns and not pipeline_df.empty)
        else 0
    )
    total_duration = (
        pipeline_df["duration_seconds"].sum(min_count=1)
        if ("duration_seconds" in pipeline_df.columns and not pipeline_df.empty)
        else pd.NA
    )

    pipeline_metric_1, pipeline_metric_2, pipeline_metric_3, pipeline_metric_4 = (
        st.columns(4)
    )
    pipeline_metric_1.metric(
        "Quy trình xử lý",
        translate_status(pipeline_status),
    )
    pipeline_metric_2.metric(
        "Số bước xử lý",
        pipeline_payload.get(
            "stage_count",
            len(pipeline_df),
        ),
    )
    pipeline_metric_3.metric(
        "Bước gặp lỗi",
        failed_stage_count,
    )
    pipeline_metric_4.metric(
        "Tổng thời gian",
        format_number(
            total_duration,
            1,
        )
        + " giây",
    )

    st.caption(f"Mã lần xử lý hiện tại: `{pipeline_batch_id}`")

    pipeline_display_df = pd.DataFrame()

    if not pipeline_df.empty:
        pipeline_display_columns = [
            column
            for column in [
                "stage_name",
                "status",
                "started_at",
                "finished_at",
                "duration_seconds",
                "input_records",
                "output_records",
                "failed_records",
                "error_message",
            ]
            if column in pipeline_df.columns
        ]
        pipeline_display_df = pipeline_df[pipeline_display_columns].copy()

        if "stage_name" in pipeline_display_df.columns:
            pipeline_display_df["stage_name"] = pipeline_display_df["stage_name"].apply(
                translate_stage
            )
        if "status" in pipeline_display_df.columns:
            pipeline_display_df["status"] = pipeline_display_df["status"].apply(
                translate_status
            )
        for datetime_column in [
            "started_at",
            "finished_at",
        ]:
            if datetime_column in pipeline_display_df.columns:
                pipeline_display_df[datetime_column] = pipeline_display_df[
                    datetime_column
                ].apply(format_datetime)

        pipeline_display_df = pipeline_display_df.rename(
            columns={
                "stage_name": "Bước xử lý",
                "status": "Trạng thái",
                "started_at": "Bắt đầu",
                "finished_at": "Kết thúc",
                "duration_seconds": "Thời gian (giây)",
                "input_records": "Dữ liệu đầu vào",
                "output_records": "Dữ liệu đầu ra",
                "failed_records": "Bản ghi lỗi",
                "error_message": "Thông báo lỗi",
            }
        )
        st.dataframe(
            pipeline_display_df,
            width="stretch",
            hide_index=True,
        )
        st.download_button(
            "Tải trạng thái quy trình xử lý",
            data=pipeline_display_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="pipeline_health.csv",
            mime="text/csv",
            key="download_pipeline_health",
        )
    else:
        st.info("Chưa có dữ liệu về quy trình xử lý.")

    st.subheader("Kiểm tra chất lượng dữ liệu")

    try:
        quality_payload = load_data_quality(snapshot_url)
        quality_df = records_to_dataframe(quality_payload.get("data", []))
    except AirQualitySnapshotError as error:
        st.warning(
            "Kết quả kiểm tra chất lượng dữ liệu đang tạm thời không truy cập được."
        )
        st.caption(str(error))
        quality_payload = {}
        quality_df = pd.DataFrame()

    quality_status = clean_text(
        quality_payload.get("status"),
        "UNKNOWN",
    )
    quality_check_count = quality_payload.get(
        "check_count",
        len(quality_df),
    )
    failed_check_count = quality_payload.get(
        "failed_check_count",
        0,
    )
    bad_record_count = (
        quality_df["bad_records_count"].sum(min_count=1)
        if ("bad_records_count" in quality_df.columns and not quality_df.empty)
        else 0
    )

    quality_metric_1, quality_metric_2, quality_metric_3, quality_metric_4 = st.columns(
        4
    )
    quality_metric_1.metric(
        "Chất lượng dữ liệu",
        translate_status(quality_status),
    )
    quality_metric_2.metric(
        "Số nội dung kiểm tra",
        quality_check_count,
    )
    quality_metric_3.metric(
        "Kiểm tra không đạt",
        failed_check_count,
    )
    quality_metric_4.metric(
        "Bản ghi có vấn đề",
        format_integer(bad_record_count),
    )

    quality_display_df = pd.DataFrame()

    if not quality_df.empty:
        quality_display_columns = [
            column
            for column in [
                "check_name",
                "status",
                "bad_records_count",
                "message",
                "checked_at",
            ]
            if column in quality_df.columns
        ]
        quality_display_df = quality_df[quality_display_columns].copy()

        if "status" in quality_display_df.columns:
            quality_display_df["status"] = quality_display_df["status"].apply(
                translate_status
            )
        if "checked_at" in quality_display_df.columns:
            quality_display_df["checked_at"] = quality_display_df["checked_at"].apply(
                format_datetime
            )

        quality_display_df = quality_display_df.rename(
            columns={
                "check_name": "Nội dung kiểm tra",
                "status": "Trạng thái",
                "bad_records_count": "Bản ghi có vấn đề",
                "message": "Kết quả",
                "checked_at": "Thời điểm kiểm tra",
            }
        )

        st.dataframe(
            quality_display_df,
            width="stretch",
            hide_index=True,
        )
        st.download_button(
            "Tải kết quả kiểm tra chất lượng",
            data=quality_display_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="data_quality.csv",
            mime="text/csv",
            key="download_data_quality",
        )
    else:
        st.info("Chưa có kết quả kiểm tra chất lượng dữ liệu.")

    with st.expander(
        "Thông tin kỹ thuật",
        expanded=False,
    ):
        technical_health = {
            "snapshot_status": health_status,
            "database": database_name,
            "batch_id": batch_id,
            "record_count": record_count,
            "point_count": len(point_ids),
            "location_count": len(location_summary_df),
            "latest_forecast_time": format_datetime(latest_forecast_time),
            "data_updated_at": format_datetime(data_updated_at),
        }
        st.json(technical_health)


render_glossary_and_footer()
