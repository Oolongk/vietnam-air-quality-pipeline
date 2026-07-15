from __future__ import annotations

import os
from typing import Any

import pandas as pd
import streamlit as st

from dashboard.api_client import (
    AirQualityAPIClient,
    AirQualityAPIError,
)


st.set_page_config(
    page_title=(
        "Vietnam Air Quality Dashboard"
    ),
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
]


def classify_aqi(
    value: float | int | None,
) -> str:
    if value is None or pd.isna(value):
        return "Không có dữ liệu"

    aqi = float(
        value
    )

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


def records_to_dataframe(
    records: list[dict[str, Any]],
) -> pd.DataFrame:
    dataframe = pd.DataFrame(
        records
    )

    if dataframe.empty:
        return dataframe

    for column in NUMERIC_COLUMNS:
        if column in dataframe.columns:
            dataframe[column] = (
                pd.to_numeric(
                    dataframe[column],
                    errors="coerce",
                )
            )

    datetime_columns = [
        "forecast_time",
        "ingested_at",
        "created_at",
        "started_at",
        "finished_at",
        "checked_at",
        "updated_at",
    ]

    for column in datetime_columns:
        if column in dataframe.columns:
            dataframe[column] = (
                pd.to_datetime(
                    dataframe[column],
                    errors="coerce",
                )
            )

    return dataframe


@st.cache_data(
    ttl=60,
    show_spinner=False,
)
def load_health(
    api_url: str,
) -> dict[str, Any]:
    client = AirQualityAPIClient(
        api_url
    )

    return client.get_health()


@st.cache_data(
    ttl=60,
    show_spinner=False,
)
def load_latest_air_quality(
    api_url: str,
) -> dict[str, Any]:
    client = AirQualityAPIClient(
        api_url
    )

    return (
        client.get_latest_air_quality(
            limit=2000
        )
    )


@st.cache_data(
    ttl=60,
    show_spinner=False,
)
def load_point_history(
    api_url: str,
    point_id: str,
) -> dict[str, Any]:
    client = AirQualityAPIClient(
        api_url
    )

    return client.get_point_history(
        point_id=point_id,
        limit=168,
    )


@st.cache_data(
    ttl=60,
    show_spinner=False,
)
def load_pipeline_health(
    api_url: str,
) -> dict[str, Any]:
    client = AirQualityAPIClient(
        api_url
    )

    return (
        client.get_pipeline_health()
    )


@st.cache_data(
    ttl=60,
    show_spinner=False,
)
def load_data_quality(
    api_url: str,
) -> dict[str, Any]:
    client = AirQualityAPIClient(
        api_url
    )

    return client.get_data_quality()


@st.cache_data(
    ttl=60,
    show_spinner=False,
)
def load_alerts(
    api_url: str,
) -> dict[str, Any]:
    client = AirQualityAPIClient(
        api_url
    )

    return client.get_latest_alerts(
        limit=100
    )


default_api_url = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000",
)


st.sidebar.header(
    "Cấu hình"
)

api_url = st.sidebar.text_input(
    label="FastAPI URL",
    value=default_api_url,
)

if st.sidebar.button(
    "Làm mới dữ liệu",
    use_container_width=True,
):
    st.cache_data.clear()
    st.rerun()


st.title(
    "Vietnam Air Quality Monitoring"
)

st.caption(
    "Dữ liệu mô hình và dự báo chất lượng "
    "không khí từ Open-Meteo, được xử lý "
    "bởi Airflow, MinIO và TimescaleDB."
)


try:
    health_payload = load_health(
        api_url
    )

except AirQualityAPIError as error:
    st.error(
        f"Không kết nối được FastAPI: {error}"
    )

    st.info(
        "Kiểm tra container API bằng "
        "`docker compose ps api`."
    )

    st.stop()


health_status = health_payload.get(
    "status",
    "UNKNOWN",
)

database_name = health_payload.get(
    "database",
    "UNKNOWN",
)

st.sidebar.success(
    f"API: {health_status}"
)

st.sidebar.write(
    f"Database: `{database_name}`"
)


try:
    latest_payload = (
        load_latest_air_quality(
            api_url
        )
    )

except AirQualityAPIError as error:
    st.error(
        "Không tải được dữ liệu AQI: "
        f"{error}"
    )

    st.stop()


records = latest_payload.get(
    "data",
    [],
)

if not isinstance(
    records,
    list,
):
    st.error(
        "Trường data của API không phải list."
    )

    st.stop()


air_quality_df = (
    records_to_dataframe(
        records
    )
)

if air_quality_df.empty:
    st.warning(
        "API chưa trả về dữ liệu AQI."
    )

    st.stop()


batch_id = latest_payload.get(
    "batch_id",
    "UNKNOWN",
)

record_count = latest_payload.get(
    "record_count",
    len(air_quality_df),
)

point_ids = sorted(
    air_quality_df[
        "point_id"
    ]
    .dropna()
    .astype(str)
    .unique()
    .tolist()
)

nearest_forecast_df = (
    air_quality_df
    .sort_values(
        by="forecast_time"
    )
    .groupby(
        "point_id",
        as_index=False,
    )
    .first()
)

average_aqi = (
    nearest_forecast_df[
        "us_aqi"
    ].mean()
    if "us_aqi"
    in nearest_forecast_df.columns
    else float("nan")
)

maximum_aqi = (
    nearest_forecast_df[
        "us_aqi"
    ].max()
    if "us_aqi"
    in nearest_forecast_df.columns
    else float("nan")
)


overview_tab, point_tab, health_tab, alert_tab = (
    st.tabs(
        [
            "Tổng quan AQI",
            "Chi tiết theo điểm",
            "Pipeline Health",
            "Cảnh báo",
        ]
    )
)


with overview_tab:
    metric_1, metric_2, metric_3, metric_4 = (
        st.columns(4)
    )

    metric_1.metric(
        label="Batch mới nhất",
        value=str(batch_id),
    )

    metric_2.metric(
        label="Số monitoring point",
        value=len(point_ids),
    )

    metric_3.metric(
        label="Tổng số records",
        value=record_count,
    )

    metric_4.metric(
        label="AQI trung bình gần nhất",
        value=(
            f"{average_aqi:.1f}"
            if not pd.isna(
                average_aqi
            )
            else "N/A"
        ),
    )

    st.subheader(
        "Chất lượng không khí gần nhất"
    )

    if not pd.isna(
        maximum_aqi
    ):
        st.write(
            "AQI cao nhất: "
            f"**{maximum_aqi:.1f}** — "
            f"**{classify_aqi(maximum_aqi)}**"
        )

    chart_columns = [
        column
        for column in [
            "point_id",
            "us_aqi",
        ]
        if column
        in nearest_forecast_df.columns
    ]

    if len(
        chart_columns
    ) == 2:
        aqi_chart_df = (
            nearest_forecast_df[
                chart_columns
            ]
            .dropna(
                subset=[
                    "us_aqi",
                ]
            )
            .set_index(
                "point_id"
            )
        )

        st.bar_chart(
            aqi_chart_df
        )

    map_columns = [
        column
        for column in [
            "latitude",
            "longitude",
        ]
        if column
        in nearest_forecast_df.columns
    ]

    if len(
        map_columns
    ) == 2:
        map_df = (
            nearest_forecast_df[
                map_columns
            ]
            .dropna()
        )

        if not map_df.empty:
            st.subheader(
                "Vị trí monitoring point"
            )

            st.map(
                map_df
            )

    display_columns = [
        column
        for column in [
            "point_id",
            "location_id",
            "forecast_time",
            "pm2_5",
            "pm10",
            "ozone",
            "us_aqi",
        ]
        if column
        in nearest_forecast_df.columns
    ]

    display_df = (
        nearest_forecast_df[
            display_columns
        ].copy()
    )

    if "us_aqi" in display_df.columns:
        display_df[
            "aqi_level"
        ] = display_df[
            "us_aqi"
        ].apply(
            classify_aqi
        )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )


with point_tab:
    selected_point_id = st.selectbox(
        label="Chọn monitoring point",
        options=point_ids,
    )

    try:
        point_payload = (
            load_point_history(
                api_url,
                selected_point_id,
            )
        )

        point_records = point_payload.get(
            "data",
            [],
        )

        point_df = (
            records_to_dataframe(
                point_records
            )
        )

    except AirQualityAPIError as error:
        st.error(
            "Không tải được dữ liệu "
            f"{selected_point_id}: {error}"
        )

        point_df = pd.DataFrame()

    if not point_df.empty:
        point_df = point_df.sort_values(
            by="forecast_time"
        )

        first_record = point_df.iloc[0]

        metric_1, metric_2, metric_3, metric_4 = (
            st.columns(4)
        )

        metric_1.metric(
            label="Point ID",
            value=selected_point_id,
        )

        metric_2.metric(
            label="PM2.5 gần nhất",
            value=(
                f"{first_record['pm2_5']:.1f}"
                if "pm2_5"
                in point_df.columns
                and not pd.isna(
                    first_record["pm2_5"]
                )
                else "N/A"
            ),
        )

        metric_3.metric(
            label="PM10 gần nhất",
            value=(
                f"{first_record['pm10']:.1f}"
                if "pm10"
                in point_df.columns
                and not pd.isna(
                    first_record["pm10"]
                )
                else "N/A"
            ),
        )

        current_aqi = (
            first_record["us_aqi"]
            if "us_aqi"
            in point_df.columns
            else None
        )

        metric_4.metric(
            label="US AQI gần nhất",
            value=(
                f"{current_aqi:.0f}"
                if current_aqi is not None
                and not pd.isna(
                    current_aqi
                )
                else "N/A"
            ),
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
            if column
            in point_df.columns
        ]

        if pollutant_columns:
            st.subheader(
                "Dự báo chất ô nhiễm theo giờ"
            )

            pollutant_chart_df = (
                point_df[
                    [
                        "forecast_time",
                        *pollutant_columns,
                    ]
                ]
                .set_index(
                    "forecast_time"
                )
            )

            st.line_chart(
                pollutant_chart_df
            )

        if "us_aqi" in point_df.columns:
            st.subheader(
                "Dự báo US AQI"
            )

            aqi_history_df = (
                point_df[
                    [
                        "forecast_time",
                        "us_aqi",
                    ]
                ]
                .set_index(
                    "forecast_time"
                )
            )

            st.line_chart(
                aqi_history_df
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
            if column
            in point_df.columns
        ]

        st.dataframe(
            point_df[
                point_display_columns
            ],
            use_container_width=True,
            hide_index=True,
        )


with health_tab:
    st.subheader(
        "Trạng thái Pipeline"
    )

    try:
        pipeline_payload = (
            load_pipeline_health(
                api_url
            )
        )

        pipeline_records = (
            pipeline_payload.get(
                "data",
                [],
            )
        )

        pipeline_df = (
            records_to_dataframe(
                pipeline_records
            )
        )

        pipeline_status = (
            pipeline_payload.get(
                "status",
                "UNKNOWN",
            )
        )

        pipeline_batch_id = (
            pipeline_payload.get(
                "batch_id",
                "UNKNOWN",
            )
        )

        metric_1, metric_2, metric_3 = (
            st.columns(3)
        )

        metric_1.metric(
            label="Pipeline status",
            value=pipeline_status,
        )

        metric_2.metric(
            label="Batch ID",
            value=str(
                pipeline_batch_id
            ),
        )

        metric_3.metric(
            label="Số stage",
            value=pipeline_payload.get(
                "stage_count",
                len(pipeline_df),
            ),
        )

        if not pipeline_df.empty:
            st.dataframe(
                pipeline_df,
                use_container_width=True,
                hide_index=True,
            )

    except AirQualityAPIError as error:
        st.warning(
            "Endpoint Pipeline Health "
            f"chưa sử dụng được: {error}"
        )

    st.subheader(
        "Data Quality"
    )

    try:
        quality_payload = (
            load_data_quality(
                api_url
            )
        )

        quality_records = (
            quality_payload.get(
                "data",
                [],
            )
        )

        quality_df = (
            records_to_dataframe(
                quality_records
            )
        )

        metric_1, metric_2, metric_3 = (
            st.columns(3)
        )

        metric_1.metric(
            label="Data Quality status",
            value=quality_payload.get(
                "status",
                "UNKNOWN",
            ),
        )

        metric_2.metric(
            label="Số checks",
            value=quality_payload.get(
                "check_count",
                len(quality_df),
            ),
        )

        metric_3.metric(
            label="Checks thất bại",
            value=quality_payload.get(
                "failed_check_count",
                0,
            ),
        )

        if not quality_df.empty:
            st.dataframe(
                quality_df,
                use_container_width=True,
                hide_index=True,
            )

    except AirQualityAPIError as error:
        st.warning(
            "Endpoint Data Quality "
            f"chưa sử dụng được: {error}"
        )


with alert_tab:
    st.subheader(
        "Cảnh báo chất lượng không khí"
    )

    try:
        alert_payload = load_alerts(
            api_url
        )

        alert_records = (
            alert_payload.get(
                "data",
                [],
            )
        )

        alert_df = (
            records_to_dataframe(
                alert_records
            )
        )

        st.metric(
            label="Số alert trả về",
            value=alert_payload.get(
                "record_count",
                len(alert_df),
            ),
        )

        if alert_df.empty:
            st.info(
                "Không có cảnh báo trong "
                "kết quả hiện tại."
            )

        else:
            st.dataframe(
                alert_df,
                use_container_width=True,
                hide_index=True,
            )

    except AirQualityAPIError as error:
        st.warning(
            "Endpoint Alert chưa sử dụng "
            f"được: {error}"
        )