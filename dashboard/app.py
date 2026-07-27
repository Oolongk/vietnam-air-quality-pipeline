from __future__ import annotations

import os
from html import escape
from textwrap import dedent
from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st

from snapshot_client import (
    AirQualitySnapshotClient,
    AirQualitySnapshotError,
)


st.set_page_config(
    page_title="Vietnam Air Quality Dashboard",
    page_icon="🌏",
    layout="wide",
)


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
]

POLLUTANT_LABELS = {
    "us_aqi": "US AQI",
    "pm2_5": "PM2.5",
    "pm10": "PM10",
    "ozone": "O₃",
    "nitrogen_dioxide": "NO₂",
    "sulphur_dioxide": "SO₂",
    "carbon_monoxide": "CO",
}

POINT_TYPE_LABELS = {
    "urban_center": "Trung tâm đô thị",
    "residential": "Khu dân cư",
    "industrial": "Khu công nghiệp",
    "traffic": "Khu vực giao thông",
    "coastal": "Khu vực ven biển",
    "suburban": "Khu vực ngoại ô",
    "rural": "Khu vực nông thôn",
    "background": "Điểm nền",
}

STAGE_LABELS = {
    "extract": "Thu thập dữ liệu",
    "transform": "Làm sạch dữ liệu",
    "data_quality": "Kiểm tra chất lượng",
    "load_timescaledb": "Nạp TimescaleDB",
    "alerts": "Xử lý cảnh báo",
    "mart": "Xây dựng Mart",
    "snapshot_publish": "Xuất bản Snapshot",
}

STATUS_LABELS = {
    "SUCCESS": "Thành công",
    "HEALTHY": "Ổn định",
    "FAILED": "Thất bại",
    "FAIL": "Thất bại",
    "WARNING": "Cảnh báo",
    "RUNNING": "Đang chạy",
    "EMPTY": "Chưa có dữ liệu",
    "OPEN": "Đang mở",
    "ACKNOWLEDGED": "Đã xác nhận",
    "RESOLVED": "Đã xử lý",
    "PASS": "Đạt",
    "PASSED": "Đạt",
}

ALERT_SEVERITY_LABELS = {
    "MEDIUM": "Trung bình",
    "HIGH": "Cao",
    "CRITICAL": "Nghiêm trọng",
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


# -----------------------------------------------------------------------------
# UI helpers
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

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f8fafc 0%, #eef4f8 100%);
            border-right: 1px solid var(--aq-border);
        }

        [data-testid="stSidebar"] .block-container {
            padding-top: 1.5rem;
        }

        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label {
            color: var(--aq-text);
        }

        [data-testid="stSidebar"] code {
            color: #047857;
            background: #e7f8f2;
        }

        [data-testid="stSidebar"] .stButton > button {
            color: white;
            background: var(--aq-primary);
            border-color: var(--aq-primary);
        }

        [data-testid="stSidebar"] .stButton > button:hover {
            color: white;
            background: var(--aq-primary-dark);
            border-color: var(--aq-primary-dark);
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
            margin-bottom: 1.4rem;
            border: 1px solid rgba(255, 255, 255, 0.55);
            border-radius: 24px;
            color: white;
            background: linear-gradient(135deg, #0f766e 0%, #0369a1 58%, #1d4ed8 100%);
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
            color: rgba(255, 255, 255, 0.78);
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
            color: rgba(255, 255, 255, 0.90);
            font-size: 1rem;
            line-height: 1.7;
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

        .aq-footer {
            margin-top: 2.5rem;
            padding-top: 1rem;
            border-top: 1px solid var(--aq-border);
            color: var(--aq-muted);
            font-size: 0.82rem;
            line-height: 1.6;
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
                padding-left: 1rem;
                padding-right: 1rem;
            }

            .aq-hero {
                padding: 1.5rem;
                border-radius: 18px;
            }

            .aq-hero__title {
                font-size: 2rem;
            }

            div[data-testid="stMetric"] {
                min-height: 106px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard_header() -> None:
    header_html = dedent(
        """
        <section class="aq-hero">
            <div class="aq-hero__eyebrow">Vietnam Air Quality Platform</div>
            <h1 class="aq-hero__title">
                Giám sát chất lượng không khí trên toàn Việt Nam
            </h1>
            <p class="aq-hero__description">
                Theo dõi dữ liệu mô hình và dự báo tại 102 điểm đại diện thuộc
                34 tỉnh, thành phố. Dữ liệu được thu thập, kiểm tra chất lượng,
                xử lý và xuất bản qua nền tảng Data Engineering gồm Airflow,
                MinIO, TimescaleDB và AWS.
            </p>
        </section>
        """
    ).strip()
    st.markdown(header_html, unsafe_allow_html=True)


def render_aqi_legend() -> None:
    st.markdown(
        """
        <div class="aq-legend">
            <span class="aq-legend__item"><span class="aq-legend__dot" style="background:#22c55e"></span>Tốt</span>
            <span class="aq-legend__item"><span class="aq-legend__dot" style="background:#eab308"></span>Trung bình</span>
            <span class="aq-legend__item"><span class="aq-legend__dot" style="background:#f97316"></span>Không tốt cho nhóm nhạy cảm</span>
            <span class="aq-legend__item"><span class="aq-legend__dot" style="background:#dc2626"></span>Không tốt</span>
            <span class="aq-legend__item"><span class="aq-legend__dot" style="background:#9333ea"></span>Rất không tốt</span>
            <span class="aq-legend__item"><span class="aq-legend__dot" style="background:#7f1d1d"></span>Nguy hiểm</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_footer() -> None:
    st.markdown(
        """
        <div class="aq-footer">
            Dữ liệu Open-Meteo là dữ liệu mô hình và dự báo theo tọa độ đại diện,
            không phải dữ liệu đo trực tiếp từ trạm quan trắc tại mọi khu vực.
            Dashboard phục vụ mục đích học tập và portfolio Data Engineering,
            không thay thế cảnh báo môi trường hoặc y tế chính thức.
        </div>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# Data formatting helpers
# -----------------------------------------------------------------------------


def clean_text(value: Any, fallback: str = "") -> str:
    if value is None or pd.isna(value):
        return fallback
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


def format_number(value: Any, decimal_places: int = 1) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.{decimal_places}f}"


def format_integer(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{int(float(value)):,}"


def format_datetime(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")

    return timestamp.tz_convert("Asia/Ho_Chi_Minh").strftime("%d/%m/%Y %H:%M")


def translate_point_type(value: Any) -> str:
    normalized = clean_text(value)
    return POINT_TYPE_LABELS.get(normalized, normalized or "Chưa phân loại")


def translate_stage(value: Any) -> str:
    normalized = clean_text(value)
    return STAGE_LABELS.get(normalized, normalized or "Chưa xác định")


def translate_status(value: Any) -> str:
    normalized = clean_text(value).upper()
    return STATUS_LABELS.get(normalized, normalized or "Không xác định")


def translate_alert_severity(value: Any) -> str:
    normalized = clean_text(value).upper()
    return ALERT_SEVERITY_LABELS.get(normalized, normalized or "Không xác định")


def records_to_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    dataframe = pd.DataFrame(records)
    if dataframe.empty:
        return dataframe

    for column in NUMERIC_COLUMNS:
        if column in dataframe.columns:
            dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

    for column in DATETIME_COLUMNS:
        if column in dataframe.columns:
            dataframe[column] = pd.to_datetime(
                dataframe[column],
                errors="coerce",
                utc=True,
            )

    for identifier_column in ["point_id", "location_id", "batch_id"]:
        if identifier_column in dataframe.columns:
            dataframe[identifier_column] = (
                dataframe[identifier_column]
                .where(dataframe[identifier_column].notna(), "")
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


def select_nearest_forecast_records(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()

    working = dataframe.copy()
    if "point_id" not in working.columns:
        return working

    if "forecast_time" not in working.columns:
        return working.drop_duplicates(subset=["point_id"], keep="first")

    now_utc = pd.Timestamp.now(tz="UTC")
    working["_forecast_distance"] = (
        working["forecast_time"] - now_utc
    ).abs()

    working = working.sort_values(
        by=["point_id", "_forecast_distance", "forecast_time"],
        ascending=[True, True, True],
        na_position="last",
    )

    return (
        working.drop_duplicates(subset=["point_id"], keep="first")
        .drop(columns=["_forecast_distance"], errors="ignore")
        .reset_index(drop=True)
    )


def build_location_summary_dataframe(nearest_dataframe: pd.DataFrame) -> pd.DataFrame:
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
        working["location_id"].where(working["location_id"].notna(), "").astype(str).str.strip()
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
        working[column_name] = pd.to_numeric(working[column_name], errors="coerce")

    summary = (
        working.groupby("location_id", as_index=False, dropna=False)
        .agg(
            location_name=("location_name", first_non_empty_value),
            latitude=("latitude", "mean"),
            longitude=("longitude", "mean"),
            monitoring_point_count=("point_id", "nunique"),
            average_us_aqi=("us_aqi", "mean"),
            maximum_us_aqi=("us_aqi", "max"),
            average_pm2_5=("pm2_5", "mean"),
            average_pm10=("pm10", "mean"),
            average_ozone=("ozone", "mean"),
            average_nitrogen_dioxide=("nitrogen_dioxide", "mean"),
            forecast_time=("forecast_time", "max"),
        )
    )

    worst_points = (
        working.sort_values(
            ["location_id", "us_aqi", "point_id"],
            ascending=[True, False, True],
            na_position="last",
        )
        .drop_duplicates("location_id", keep="first")
        [["location_id", "point_id", "point_name", "us_aqi"]]
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
        lambda row: clean_text(row.get("location_name"), clean_text(row.get("location_id"), "Không rõ")),
        axis=1,
    )
    summary["aqi_level"] = summary["average_us_aqi"].apply(classify_aqi)
    summary["fill_color"] = summary["average_us_aqi"].apply(get_aqi_color)
    summary["marker_radius"] = (
        summary["average_us_aqi"]
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
    summary[round_columns] = summary[round_columns].round(2)

    return summary.sort_values(
        ["average_us_aqi", "maximum_us_aqi"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)


def get_selected_location_from_map(map_event: Any) -> str | None:
    if map_event is None:
        return None

    selection = getattr(map_event, "selection", None)
    if selection is None and hasattr(map_event, "get"):
        selection = map_event.get("selection")
    if not selection:
        return None

    objects = getattr(selection, "objects", None)
    if objects is None and hasattr(selection, "get"):
        objects = selection.get("objects", {})
    if not objects or not hasattr(objects, "get"):
        return None

    selected_objects = objects.get("location-markers", [])
    if not selected_objects:
        return None

    location_id = clean_text(selected_objects[0].get("location_id"))
    return location_id or None


# -----------------------------------------------------------------------------
# Snapshot access
# -----------------------------------------------------------------------------


@st.cache_data(ttl=60, show_spinner=False)
def load_health(snapshot_url: str) -> dict[str, Any]:
    return AirQualitySnapshotClient(snapshot_url).get_health()


@st.cache_data(ttl=60, show_spinner=False)
def load_latest_air_quality(snapshot_url: str) -> dict[str, Any]:
    return AirQualitySnapshotClient(snapshot_url).get_latest_air_quality(limit=5000)


@st.cache_data(ttl=60, show_spinner=False)
def load_point_history(snapshot_url: str, point_id: str) -> dict[str, Any]:
    return AirQualitySnapshotClient(snapshot_url).get_point_history(
        point_id=point_id,
        limit=168,
    )


@st.cache_data(ttl=60, show_spinner=False)
def load_pipeline_health(snapshot_url: str) -> dict[str, Any]:
    return AirQualitySnapshotClient(snapshot_url).get_pipeline_health()


@st.cache_data(ttl=60, show_spinner=False)
def load_data_quality(snapshot_url: str) -> dict[str, Any]:
    return AirQualitySnapshotClient(snapshot_url).get_data_quality()


@st.cache_data(ttl=60, show_spinner=False)
def load_alerts(snapshot_url: str) -> dict[str, Any]:
    return AirQualitySnapshotClient(snapshot_url).get_latest_alerts(limit=100)


def get_default_snapshot_url() -> str:
    environment_url = os.getenv("PUBLIC_SNAPSHOT_BASE_URL", "").strip()
    if environment_url:
        return environment_url

    try:
        secret_url = st.secrets["PUBLIC_SNAPSHOT_BASE_URL"]
    except (KeyError, FileNotFoundError):
        return ""

    return str(secret_url).strip()


# -----------------------------------------------------------------------------
# Bootstrap
# -----------------------------------------------------------------------------


inject_dashboard_styles()
render_dashboard_header()

default_snapshot_url = get_default_snapshot_url()
snapshot_url = default_snapshot_url

st.sidebar.header("Vietnam Air Quality")
st.sidebar.caption("Theo dõi snapshot công khai và trạng thái xử lý dữ liệu.")

with st.sidebar.expander("Cấu hình kỹ thuật", expanded=not bool(default_snapshot_url)):
    override_snapshot_url = st.text_input(
        label="Public Snapshot URL",
        value="",
        placeholder="https://xxxx.lambda-url.ap-southeast-2.on.aws",
        type="password",
        help="Để trống để dùng URL từ Environment hoặc Streamlit Secrets.",
    )
    if override_snapshot_url.strip():
        snapshot_url = override_snapshot_url.strip()
    elif default_snapshot_url:
        st.caption("Đang dùng URL từ Environment hoặc Streamlit Secrets.")

if st.sidebar.button("Làm mới dữ liệu", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

if not snapshot_url.strip():
    st.warning("Chưa cấu hình Public Snapshot URL.")
    st.info(
        "Đặt biến môi trường `PUBLIC_SNAPSHOT_BASE_URL`, cấu hình Streamlit Secrets "
        "hoặc nhập URL trong phần Cấu hình kỹ thuật."
    )
    st.stop()

try:
    health_payload = load_health(snapshot_url)
except AirQualitySnapshotError as error:
    st.error(f"Không đọc được public snapshot: {error}")
    st.info("Kiểm tra Lambda Function URL và đường dẫn `/current.json`.")
    st.stop()

health_status = clean_text(health_payload.get("status"), "UNKNOWN")
database_name = clean_text(health_payload.get("database"), "UNKNOWN")

if health_status.upper() in {"HEALTHY", "SUCCESS"}:
    st.sidebar.success(f"Snapshot: {translate_status(health_status)}")
else:
    st.sidebar.warning(f"Snapshot: {translate_status(health_status)}")
st.sidebar.caption(f"Database: `{database_name}`")

try:
    latest_payload = load_latest_air_quality(snapshot_url)
except AirQualitySnapshotError as error:
    st.error(f"Không tải được dữ liệu AQI: {error}")
    st.stop()

records = latest_payload.get("data", [])
if not isinstance(records, list):
    st.error("Trường data của API không phải list.")
    st.stop()

air_quality_df = records_to_dataframe(records)
if air_quality_df.empty:
    st.warning("API chưa trả về dữ liệu AQI.")
    st.stop()

batch_id = clean_text(latest_payload.get("batch_id"), "UNKNOWN")
record_count = latest_payload.get("record_count", len(air_quality_df))

point_ids = sorted(
    air_quality_df["point_id"].dropna().astype(str).str.strip().loc[lambda series: series.ne("")].unique().tolist()
)

point_name_lookup = (
    air_quality_df[["point_id", "point_name"]]
    .dropna(subset=["point_id"])
    .drop_duplicates(subset=["point_id"], keep="first")
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
    .drop_duplicates(subset=["point_id"], keep="first")
    .set_index("point_id")["location_id"]
    .fillna("")
    .astype(str)
    .to_dict()
    if "location_id" in air_quality_df.columns
    else {}
)


def get_point_display_name(point_id: str) -> str:
    point_name = clean_text(point_name_lookup.get(point_id))
    return point_name or "Điểm theo dõi chưa đặt tên"


nearest_forecast_df = select_nearest_forecast_records(air_quality_df)
location_summary_df = build_location_summary_dataframe(nearest_forecast_df)

location_labels = {
    clean_text(row.location_id): clean_text(row.location_label, clean_text(row.location_id))
    for row in location_summary_df[["location_id", "location_label"]].itertuples(index=False)
}

nearest_forecast_df["location_id"] = (
    nearest_forecast_df["location_id"].where(nearest_forecast_df["location_id"].notna(), "").astype(str).str.strip()
)
nearest_forecast_df["location_label"] = nearest_forecast_df["location_id"].map(location_labels)

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

st.sidebar.caption(f"Batch: `{batch_id}`")
st.sidebar.caption(f"Cập nhật dữ liệu: {format_datetime(latest_forecast_time)}")

(
    map_tab,
    analytics_tab,
    point_tab,
    alert_tab,
    operations_tab,
) = st.tabs(
    [
        "Bản đồ AQI",
        "Phân tích dữ liệu",
        "Các điểm theo dõi",
        "Cảnh báo",
        "Vận hành hệ thống",
    ]
)


# -----------------------------------------------------------------------------
# Page 1: Interactive map
# -----------------------------------------------------------------------------


with map_tab:
    st.subheader("Bản đồ chất lượng không khí Việt Nam")
    st.caption(
        "Mỗi chấm đại diện cho một tỉnh/thành. Bấm vào chấm để xem chỉ số trung bình "
        "và chi tiết các điểm theo dõi của khu vực đó."
    )
    render_aqi_legend()

    overview_1, overview_2, overview_3, overview_4 = st.columns(4)
    overview_1.metric("Tỉnh/thành", len(location_summary_df))
    overview_2.metric("Điểm theo dõi", len(point_ids))
    overview_3.metric("AQI trung bình", format_number(average_aqi))
    overview_4.metric("AQI cao nhất", format_number(maximum_aqi, 0))

    if location_summary_df.empty:
        st.warning("Không có dữ liệu tỉnh/thành để hiển thị bản đồ.")
    else:
        valid_location_ids = set(location_summary_df["location_id"].astype(str))

        stored_map_state = st.session_state.get("location_aqi_map")
        selected_from_state = get_selected_location_from_map(stored_map_state)
        if selected_from_state in valid_location_ids:
            st.session_state["selected_location_id"] = selected_from_state

        selected_location_id = st.session_state.get("selected_location_id")
        if selected_location_id not in valid_location_ids:
            selected_location_id = str(location_summary_df.iloc[0]["location_id"])
            st.session_state["selected_location_id"] = selected_location_id

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
        map_data["monitoring_point_count"] = map_data["monitoring_point_count"].astype(int)

        map_column, detail_column = st.columns([1.65, 1], gap="large")

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
                map_data["location_id"].astype(str) == str(selected_location_id)
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
                map_style=None,
                initial_view_state=pdk.ViewState(
                    latitude=16.2,
                    longitude=106.3,
                    zoom=4.65,
                    pitch=0,
                    bearing=0,
                ),
                layers=[location_layer, selected_layer],
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
                height=610,
                on_select="rerun",
                selection_mode="single-object",
                key="location_aqi_map",
            )

        selected_from_map = get_selected_location_from_map(map_event)
        if selected_from_map in valid_location_ids:
            selected_location_id = str(selected_from_map)
            st.session_state["selected_location_id"] = selected_location_id

        selected_location_row = location_summary_df.loc[
            location_summary_df["location_id"].astype(str) == selected_location_id
        ].iloc[0]

        selected_points_df = (
            nearest_forecast_df.loc[
                nearest_forecast_df["location_id"].astype(str) == selected_location_id
            ]
            .copy()
            .sort_values(by="us_aqi", ascending=False, na_position="last")
        )

        with detail_column:
            st.markdown(f"### {escape(clean_text(selected_location_row['location_label'], selected_location_id))}")
            st.caption(
                "Giá trị trung bình từ "
                f"{int(selected_location_row['monitoring_point_count'])} điểm theo dõi đại diện."
            )

            metric_1, metric_2 = st.columns(2)
            metric_1.metric(
                "US AQI trung bình",
                format_number(selected_location_row["average_us_aqi"], 1),
            )
            metric_2.metric(
                "US AQI cao nhất",
                format_number(selected_location_row["maximum_us_aqi"], 0),
            )

            aqi_level = clean_text(selected_location_row["aqi_level"], "Không có dữ liệu")
            if aqi_level in {"Tốt", "Trung bình"}:
                st.success(f"Mức chất lượng không khí: **{aqi_level}**")
            elif aqi_level == "Không có dữ liệu":
                st.info("Chưa có dữ liệu phân loại AQI.")
            else:
                st.warning(f"Mức chất lượng không khí: **{aqi_level}**")

            pollutant_1, pollutant_2 = st.columns(2)
            pollutant_1.metric(
                "PM2.5 TB (µg/m³)",
                format_number(selected_location_row["average_pm2_5"]),
            )
            pollutant_2.metric(
                "PM10 TB (µg/m³)",
                format_number(selected_location_row["average_pm10"]),
            )

            pollutant_3, pollutant_4 = st.columns(2)
            pollutant_3.metric(
                "O₃ TB (µg/m³)",
                format_number(selected_location_row["average_ozone"]),
            )
            pollutant_4.metric(
                "NO₂ TB (µg/m³)",
                format_number(selected_location_row["average_nitrogen_dioxide"]),
            )

            worst_point_name = clean_text(selected_location_row.get("worst_point_name"))
            worst_point_id = clean_text(selected_location_row.get("worst_point_id"))
            worst_point_text = worst_point_name or get_point_display_name(worst_point_id)
            st.markdown(f"**Điểm có AQI cao nhất:** {escape(worst_point_text)}")
            st.caption(
                "Thời điểm dữ liệu: "
                + format_datetime(selected_location_row.get("forecast_time"))
            )

        with st.expander(
            f"Xem chi tiết {len(selected_points_df)} điểm theo dõi",
            expanded=False,
        ):
            st.caption(
                "Các vị trí dưới đây là tọa độ lấy mẫu mô hình đại diện, "
                "không nhất thiết là trạm quan trắc vật lý."
            )

            detail_columns = [
                column
                for column in [
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
                point_detail_df["point_type"] = point_detail_df["point_type"].apply(translate_point_type)
            if "us_aqi" in point_detail_df.columns:
                point_detail_df["aqi_level"] = point_detail_df["us_aqi"].apply(classify_aqi)
            if "forecast_time" in point_detail_df.columns:
                point_detail_df["forecast_time"] = point_detail_df["forecast_time"].apply(format_datetime)

            point_detail_df = point_detail_df.rename(
                columns={
                    "point_name": "Tên khu vực",
                    "point_type": "Loại khu vực",
                    "latitude": "Vĩ độ",
                    "longitude": "Kinh độ",
                    "us_aqi": "US AQI",
                    "pm2_5": "PM2.5",
                    "pm10": "PM10",
                    "ozone": "O₃",
                    "nitrogen_dioxide": "NO₂",
                    "forecast_time": "Thời điểm",
                    "aqi_level": "Mức AQI",
                }
            )
            st.dataframe(point_detail_df, width="stretch", hide_index=True)

            selected_location_point_ids = (
                selected_points_df["point_id"].dropna().astype(str).tolist()
            )
            if selected_location_point_ids:
                selected_detail_point = st.selectbox(
                    "Chọn điểm theo dõi để xem biểu đồ 24 giờ",
                    options=selected_location_point_ids,
                    format_func=get_point_display_name,
                    key=f"map_detail_point_{selected_location_id}",
                )

                show_detail_chart = st.toggle(
                    "Hiển thị biểu đồ dự báo",
                    value=False,
                    key=f"map_detail_chart_{selected_location_id}",
                )

                if show_detail_chart:
                    try:
                        point_payload = load_point_history(snapshot_url, selected_detail_point)
                        point_history_df = records_to_dataframe(point_payload.get("data", []))
                    except AirQualitySnapshotError as error:
                        st.warning(
                            "Không tải được biểu đồ cho "
                            f"{get_point_display_name(selected_detail_point)}: {error}"
                        )
                        point_history_df = pd.DataFrame()

                    if not point_history_df.empty:
                        point_history_df = point_history_df.sort_values("forecast_time")

                        if "us_aqi" in point_history_df.columns:
                            st.markdown("#### Dự báo US AQI")
                            aqi_chart = point_history_df[["forecast_time", "us_aqi"]].set_index("forecast_time")
                            aqi_chart = aqi_chart.rename(columns={"us_aqi": "US AQI"})
                            st.line_chart(aqi_chart, width="stretch")

                        pollutant_columns = [
                            column
                            for column in [
                                "pm2_5",
                                "pm10",
                                "ozone",
                                "nitrogen_dioxide",
                                "sulphur_dioxide",
                            ]
                            if column in point_history_df.columns
                        ]
                        if pollutant_columns:
                            st.markdown("#### Dự báo chất ô nhiễm theo giờ")
                            pollutant_chart = point_history_df[
                                ["forecast_time", *pollutant_columns]
                            ].set_index("forecast_time")
                            pollutant_chart = pollutant_chart.rename(columns=POLLUTANT_LABELS)
                            st.line_chart(pollutant_chart, width="stretch")


# -----------------------------------------------------------------------------
# Page 2: Analytics
# -----------------------------------------------------------------------------


with analytics_tab:
    st.subheader("Phân tích dữ liệu")
    st.caption(
        "Phân tích dữ liệu theo giờ, so sánh tỉnh/thành và khám phá "
        "các trường kỹ thuật phục vụ Data Engineering."
    )

    metric_1, metric_2, metric_3 = st.columns(3)
    metric_1.metric("Số điểm theo dõi", len(point_ids))
    metric_2.metric("Tổng số records", record_count)
    metric_3.metric(
        "AQI trung bình gần nhất",
        format_number(average_aqi, 1),
    )

    ranking_column, distribution_column = st.columns(2, gap="large")

    with ranking_column:
        st.markdown("#### Top tỉnh/thành theo AQI")
        ranking_df = (
            location_summary_df[["location_label", "average_us_aqi"]]
            .dropna(subset=["average_us_aqi"])
            .head(15)
            .sort_values("average_us_aqi", ascending=True)
            .set_index("location_label")
            .rename(columns={"average_us_aqi": "AQI trung bình"})
        )
        st.bar_chart(ranking_df, width="stretch")

    with distribution_column:
        st.markdown("#### Phân bố mức AQI")
        distribution_series = location_summary_df["aqi_level"].value_counts()
        distribution_series = distribution_series.reindex(AQI_ORDER, fill_value=0)
        distribution_df = distribution_series.loc[lambda series: series.gt(0)].rename_axis("Mức AQI").to_frame("Số tỉnh/thành")
        st.bar_chart(distribution_df, width="stretch")

    st.markdown("#### Bộ lọc dữ liệu theo giờ")

    filter_1, filter_2 = st.columns(2)
    with filter_1:
        location_options = [
            "Tất cả tỉnh/thành",
            *location_summary_df["location_label"].astype(str).tolist(),
        ]
        selected_location = st.selectbox(
            "Tỉnh/thành",
            options=location_options,
            key="analytics_location_filter",
        )

    if selected_location == "Tất cả tỉnh/thành":
        analytics_df = air_quality_df.copy()
    else:
        selected_analytics_location_id = str(
            location_summary_df.loc[
                location_summary_df["location_label"] == selected_location,
                "location_id",
            ].iloc[0]
        )
        analytics_df = air_quality_df.loc[
            air_quality_df["location_id"].astype(str) == selected_analytics_location_id
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
            placeholder="Để trống để xem toàn bộ",
            key="analytics_point_filter",
        )

    if selected_points:
        analytics_df = analytics_df.loc[
            analytics_df["point_id"].astype(str).isin(selected_points)
        ].copy()

    available_metrics = [
        column
        for column in [
            "us_aqi",
            "pm2_5",
            "pm10",
            "ozone",
            "nitrogen_dioxide",
            "sulphur_dioxide",
        ]
        if column in analytics_df.columns
    ]

    selected_metrics = st.multiselect(
        "Thông số biểu đồ",
        options=available_metrics,
        default=[
            column
            for column in ["us_aqi", "pm2_5", "pm10"]
            if column in available_metrics
        ],
        format_func=lambda column: POLLUTANT_LABELS.get(column, column),
        key="analytics_metric_filter",
    )

    if selected_metrics and not analytics_df.empty:
        hourly_chart_df = (
            analytics_df[["forecast_time", *selected_metrics]]
            .dropna(subset=["forecast_time"])
            .groupby("forecast_time")[selected_metrics]
            .mean()
            .sort_index()
            .rename(columns=POLLUTANT_LABELS)
        )
        st.line_chart(hourly_chart_df, width="stretch")
    else:
        st.info("Chọn ít nhất một thông số để hiển thị biểu đồ.")

    st.markdown("#### Bảng dữ liệu kỹ thuật")
    st.caption(
        "Bảng giữ tên cột kỹ thuật để thể hiện schema, batch lineage và thời điểm ingestion."
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
    st.dataframe(technical_df, width="stretch", hide_index=True)

    st.download_button(
        "Tải dữ liệu đã lọc (.csv)",
        data=technical_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="air_quality_filtered.csv",
        mime="text/csv",
        use_container_width=False,
    )


# -----------------------------------------------------------------------------
# Page 3: Monitoring points
# -----------------------------------------------------------------------------


with point_tab:
    st.subheader("Chi tiết điểm theo dõi")
    st.caption(
        "Chọn một vị trí đại diện để xem thông tin khu vực và dự báo theo giờ."
    )

    selected_point_id = st.selectbox(
        "Chọn điểm theo dõi",
        options=point_ids,
        format_func=get_point_display_name,
    )

    try:
        point_payload = load_point_history(snapshot_url, selected_point_id)
        point_df = records_to_dataframe(point_payload.get("data", []))
    except AirQualitySnapshotError as error:
        st.error(
            "Không tải được dữ liệu cho "
            f"{get_point_display_name(selected_point_id)}: {error}"
        )
        point_df = pd.DataFrame()

    if point_df.empty:
        st.info("Điểm theo dõi này chưa có dữ liệu lịch sử hoặc dự báo.")
    else:
        point_df = point_df.sort_values("forecast_time")
        nearest_point_df = select_nearest_forecast_records(point_df)
        first_record = nearest_point_df.iloc[0] if not nearest_point_df.empty else point_df.iloc[0]

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
            location_labels.get(selected_location_id, selected_location_id),
        )
        selected_point_type = translate_point_type(first_record.get("point_type"))

        st.markdown(f"### {escape(selected_point_name)}")
        detail_parts = [part for part in [selected_location_name, selected_point_type] if part]
        if detail_parts:
            st.caption(" · ".join(detail_parts))

        latitude = first_record.get("latitude")
        longitude = first_record.get("longitude")
        if latitude is not None and longitude is not None and not pd.isna(latitude) and not pd.isna(longitude):
            st.caption(f"Tọa độ đại diện: {float(latitude):.5f}, {float(longitude):.5f}")

        metric_1, metric_2, metric_3 = st.columns(3)
        metric_1.metric(
            "PM2.5 gần nhất (µg/m³)",
            format_number(first_record.get("pm2_5")),
        )
        metric_2.metric(
            "PM10 gần nhất (µg/m³)",
            format_number(first_record.get("pm10")),
        )
        current_aqi = first_record.get("us_aqi")
        metric_3.metric("US AQI gần nhất", format_number(current_aqi, 0))

        current_level = classify_aqi(current_aqi)
        if current_level in {"Tốt", "Trung bình"}:
            st.success(f"Mức chất lượng không khí gần nhất: **{current_level}**")
        else:
            st.warning(f"Mức chất lượng không khí gần nhất: **{current_level}**")

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

        if "us_aqi" in point_df.columns:
            st.subheader("Dự báo US AQI")
            aqi_history_df = point_df[["forecast_time", "us_aqi"]].set_index("forecast_time")
            aqi_history_df = aqi_history_df.rename(columns={"us_aqi": "US AQI"})
            st.line_chart(aqi_history_df, width="stretch")

        if pollutant_columns:
            st.subheader("Dự báo chất ô nhiễm theo giờ")
            pollutant_chart_df = point_df[
                ["forecast_time", *pollutant_columns]
            ].set_index("forecast_time")
            pollutant_chart_df = pollutant_chart_df.rename(columns=POLLUTANT_LABELS)
            st.line_chart(pollutant_chart_df, width="stretch")

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
            point_display_df["forecast_time"] = point_display_df["forecast_time"].apply(format_datetime)
        point_display_df = point_display_df.rename(
            columns={
                "forecast_time": "Thời điểm",
                **POLLUTANT_LABELS,
            }
        )
        st.dataframe(point_display_df, width="stretch", hide_index=True)


# -----------------------------------------------------------------------------
# Page 4: Alerts
# -----------------------------------------------------------------------------


with alert_tab:
    st.subheader("Cảnh báo chất lượng không khí")
    st.caption(
        "Theo dõi các điểm có US AQI vượt ngưỡng và lọc cảnh báo theo mức độ hoặc khu vực."
    )

    try:
        alert_payload = load_alerts(snapshot_url)
        alert_df = records_to_dataframe(alert_payload.get("data", []))
    except AirQualitySnapshotError as error:
        st.warning(f"Endpoint cảnh báo chưa sử dụng được: {error}")
        alert_df = pd.DataFrame()

    if alert_df.empty:
        st.info("Không có cảnh báo trong snapshot hiện tại.")
    else:
        if "point_id" in alert_df.columns:
            alert_df["point_name"] = alert_df["point_id"].astype(str).map(point_name_lookup)
            alert_df["point_name"] = alert_df.apply(
                lambda row: clean_text(row.get("point_name"), get_point_display_name(clean_text(row.get("point_id")))),
                axis=1,
            )
        if "location_id" in alert_df.columns:
            alert_df["location_label"] = alert_df["location_id"].astype(str).map(location_labels)
            alert_df["location_label"] = alert_df.apply(
                lambda row: clean_text(row.get("location_label"), clean_text(row.get("location_id"), "Không rõ")),
                axis=1,
            )

        total_alerts = len(alert_df)
        critical_alerts = int(
            alert_df["severity"].astype(str).str.upper().eq("CRITICAL").sum()
        ) if "severity" in alert_df.columns else 0
        high_alerts = int(
            alert_df["severity"].astype(str).str.upper().eq("HIGH").sum()
        ) if "severity" in alert_df.columns else 0
        open_alerts = int(
            alert_df["status"].astype(str).str.upper().eq("OPEN").sum()
        ) if "status" in alert_df.columns else total_alerts

        alert_metric_1, alert_metric_2, alert_metric_3, alert_metric_4 = st.columns(4)
        alert_metric_1.metric("Tổng cảnh báo", total_alerts)
        alert_metric_2.metric("Nghiêm trọng", critical_alerts)
        alert_metric_3.metric("Mức cao", high_alerts)
        alert_metric_4.metric("Đang mở", open_alerts)

        filter_1, filter_2, filter_3 = st.columns(3)

        with filter_1:
            severity_values = (
                sorted(alert_df["severity"].dropna().astype(str).str.upper().unique().tolist())
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
                sorted(alert_df["location_label"].dropna().astype(str).unique().tolist())
                if "location_label" in alert_df.columns
                else []
            )
            selected_alert_location = st.selectbox(
                "Tỉnh/thành",
                options=["Tất cả tỉnh/thành", *alert_location_values],
                key="alert_location_filter",
            )

        with filter_3:
            alert_status_values = (
                sorted(alert_df["status"].dropna().astype(str).str.upper().unique().tolist())
                if "status" in alert_df.columns
                else []
            )
            selected_alert_status = st.selectbox(
                "Trạng thái",
                options=["Tất cả trạng thái", *alert_status_values],
                format_func=lambda value: (
                    value if value.startswith("Tất cả") else translate_status(value)
                ),
                key="alert_status_filter",
            )

        filtered_alert_df = alert_df.copy()
        if severity_values and selected_severities:
            filtered_alert_df = filtered_alert_df.loc[
                filtered_alert_df["severity"].astype(str).str.upper().isin(selected_severities)
            ].copy()
        elif severity_values and not selected_severities:
            filtered_alert_df = filtered_alert_df.iloc[0:0].copy()

        if selected_alert_location != "Tất cả tỉnh/thành":
            filtered_alert_df = filtered_alert_df.loc[
                filtered_alert_df["location_label"] == selected_alert_location
            ].copy()

        if selected_alert_status != "Tất cả trạng thái" and "status" in filtered_alert_df.columns:
            filtered_alert_df = filtered_alert_df.loc[
                filtered_alert_df["status"].astype(str).str.upper() == selected_alert_status
            ].copy()

        chart_column, summary_column = st.columns([1.25, 1], gap="large")
        with chart_column:
            st.markdown("#### Cảnh báo theo mức độ")
            if "severity" in filtered_alert_df.columns and not filtered_alert_df.empty:
                severity_chart = (
                    filtered_alert_df["severity"]
                    .astype(str)
                    .str.upper()
                    .map(translate_alert_severity)
                    .value_counts()
                    .rename_axis("Mức cảnh báo")
                    .to_frame("Số cảnh báo")
                )
                st.bar_chart(severity_chart, width="stretch")
            else:
                st.info("Không có dữ liệu phù hợp với bộ lọc.")

        with summary_column:
            st.markdown("#### Khu vực cần chú ý")
            if "location_label" in filtered_alert_df.columns and not filtered_alert_df.empty:
                top_alert_locations = (
                    filtered_alert_df["location_label"]
                    .value_counts()
                    .head(8)
                    .rename_axis("Tỉnh/thành")
                    .to_frame("Số cảnh báo")
                )
                st.bar_chart(top_alert_locations, width="stretch")
            else:
                st.info("Không có dữ liệu phù hợp với bộ lọc.")

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
            alert_display_df["alert_time"] = alert_display_df["alert_time"].apply(format_datetime)
        if "severity" in alert_display_df.columns:
            alert_display_df["severity"] = alert_display_df["severity"].apply(translate_alert_severity)
        if "status" in alert_display_df.columns:
            alert_display_df["status"] = alert_display_df["status"].apply(translate_status)

        alert_display_df = alert_display_df.rename(
            columns={
                "alert_time": "Thời điểm",
                "location_label": "Tỉnh/thành",
                "point_name": "Điểm theo dõi",
                "aqi_value": "US AQI",
                "aqi_level": "Mức AQI",
                "severity": "Mức cảnh báo",
                "status": "Trạng thái",
                "message": "Nội dung",
            }
        )

        if alert_display_df.empty:
            st.info("Không có cảnh báo phù hợp với bộ lọc hiện tại.")
        else:
            st.dataframe(alert_display_df, width="stretch", hide_index=True)


# -----------------------------------------------------------------------------
# Page 5: Operations and data quality
# -----------------------------------------------------------------------------


with operations_tab:
    st.subheader("Vận hành hệ thống")
    st.caption(
        "Theo dõi trạng thái từng stage, khối lượng dữ liệu và kết quả kiểm tra chất lượng."
    )

    try:
        pipeline_payload = load_pipeline_health(snapshot_url)
        pipeline_df = records_to_dataframe(pipeline_payload.get("data", []))
        pipeline_status = clean_text(pipeline_payload.get("status"), "UNKNOWN")
        pipeline_batch_id = clean_text(pipeline_payload.get("batch_id"), "UNKNOWN")
    except AirQualitySnapshotError as error:
        st.warning(f"Endpoint Pipeline Health chưa sử dụng được: {error}")
        pipeline_payload = {}
        pipeline_df = pd.DataFrame()
        pipeline_status = "UNKNOWN"
        pipeline_batch_id = "UNKNOWN"

    failed_stage_count = (
        int((~pipeline_df["status"].astype(str).str.upper().eq("SUCCESS")).sum())
        if "status" in pipeline_df.columns and not pipeline_df.empty
        else 0
    )
    total_duration = (
        pipeline_df["duration_seconds"].sum(min_count=1)
        if "duration_seconds" in pipeline_df.columns and not pipeline_df.empty
        else pd.NA
    )

    pipeline_metric_1, pipeline_metric_2, pipeline_metric_3, pipeline_metric_4 = st.columns(4)
    pipeline_metric_1.metric("Pipeline", translate_status(pipeline_status))
    pipeline_metric_2.metric("Số stage", pipeline_payload.get("stage_count", len(pipeline_df)))
    pipeline_metric_3.metric("Stage lỗi", failed_stage_count)
    pipeline_metric_4.metric(
        "Tổng thời gian (giây)",
        format_number(total_duration, 1),
    )

    st.caption(f"Batch hiện tại: `{pipeline_batch_id}`")

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
            pipeline_display_df["stage_name"] = pipeline_display_df["stage_name"].apply(translate_stage)
        if "status" in pipeline_display_df.columns:
            pipeline_display_df["status"] = pipeline_display_df["status"].apply(translate_status)
        for datetime_column in ["started_at", "finished_at"]:
            if datetime_column in pipeline_display_df.columns:
                pipeline_display_df[datetime_column] = pipeline_display_df[datetime_column].apply(format_datetime)

        pipeline_display_df = pipeline_display_df.rename(
            columns={
                "stage_name": "Stage",
                "status": "Trạng thái",
                "started_at": "Bắt đầu",
                "finished_at": "Kết thúc",
                "duration_seconds": "Thời gian (giây)",
                "input_records": "Input",
                "output_records": "Output",
                "failed_records": "Lỗi",
                "error_message": "Thông báo lỗi",
            }
        )
        st.dataframe(pipeline_display_df, width="stretch", hide_index=True)
    else:
        st.info("Chưa có dữ liệu Pipeline Health.")

    st.subheader("Data Quality")

    try:
        quality_payload = load_data_quality(snapshot_url)
        quality_df = records_to_dataframe(quality_payload.get("data", []))
    except AirQualitySnapshotError as error:
        st.warning(f"Endpoint Data Quality chưa sử dụng được: {error}")
        quality_payload = {}
        quality_df = pd.DataFrame()

    quality_status = clean_text(quality_payload.get("status"), "UNKNOWN")
    quality_check_count = quality_payload.get("check_count", len(quality_df))
    failed_check_count = quality_payload.get("failed_check_count", 0)
    bad_record_count = (
        quality_df["bad_records_count"].sum(min_count=1)
        if "bad_records_count" in quality_df.columns and not quality_df.empty
        else 0
    )

    quality_metric_1, quality_metric_2, quality_metric_3, quality_metric_4 = st.columns(4)
    quality_metric_1.metric("Data Quality", translate_status(quality_status))
    quality_metric_2.metric("Số checks", quality_check_count)
    quality_metric_3.metric("Checks thất bại", failed_check_count)
    quality_metric_4.metric("Bad records", format_integer(bad_record_count))

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
            quality_display_df["status"] = quality_display_df["status"].apply(translate_status)
        if "checked_at" in quality_display_df.columns:
            quality_display_df["checked_at"] = quality_display_df["checked_at"].apply(format_datetime)

        quality_display_df = quality_display_df.rename(
            columns={
                "check_name": "Kiểm tra",
                "status": "Trạng thái",
                "bad_records_count": "Bad records",
                "message": "Kết quả",
                "checked_at": "Thời điểm kiểm tra",
            }
        )
        st.dataframe(quality_display_df, width="stretch", hide_index=True)
    else:
        st.info("Chưa có dữ liệu Data Quality.")

    with st.expander("Thông tin kỹ thuật của snapshot", expanded=False):
        technical_health = {
            "snapshot_status": health_status,
            "database": database_name,
            "batch_id": batch_id,
            "record_count": record_count,
            "point_count": len(point_ids),
            "location_count": len(location_summary_df),
            "latest_forecast_time": format_datetime(latest_forecast_time),
        }
        st.json(technical_health)


render_footer()
