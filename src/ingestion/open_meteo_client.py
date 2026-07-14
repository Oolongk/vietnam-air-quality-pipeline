from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Sequence

import requests
from dotenv import load_dotenv
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


DEFAULT_HOURLY_VARIABLES: tuple[str, ...] = (
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
)

RETRYABLE_HTTP_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}


class OpenMeteoClientError(RuntimeError):
    """Lỗi chung khi giao tiếp với Open-Meteo API."""


class RetryableOpenMeteoError(OpenMeteoClientError):
    """Lỗi tạm thời có thể thử gọi lại."""


class InvalidOpenMeteoResponseError(OpenMeteoClientError):
    """API phản hồi thành công nhưng cấu trúc dữ liệu không hợp lệ."""


class OpenMeteoClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        hourly_variables: Sequence[str] | None = None,
    ) -> None:
        load_dotenv()

        configured_url = (
            base_url
            or os.getenv("OPEN_METEO_AIR_QUALITY_URL")
        )

        if not configured_url:
            raise OpenMeteoClientError(
                "Chưa cấu hình OPEN_METEO_AIR_QUALITY_URL."
            )

        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds phải lớn hơn 0."
            )

        selected_variables = tuple(
            hourly_variables
            or DEFAULT_HOURLY_VARIABLES
        )

        if not selected_variables:
            raise ValueError(
                "Danh sách hourly_variables không được rỗng."
            )

        self.base_url = configured_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.hourly_variables = selected_variables

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "vietnam-air-quality-pipeline/1.0"
                )
            }
        )

    @staticmethod
    def _validate_identifier(
        value: str,
        field_name: str,
    ) -> str:
        if not isinstance(value, str):
            raise TypeError(
                f"{field_name} phải là chuỗi."
            )

        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError(
                f"{field_name} không được rỗng."
            )

        return cleaned_value

    @staticmethod
    def _validate_coordinates(
        latitude: float,
        longitude: float,
    ) -> tuple[float, float]:
        try:
            latitude_value = float(latitude)
            longitude_value = float(longitude)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Latitude và longitude phải là số."
            ) from error

        if not -90 <= latitude_value <= 90:
            raise ValueError(
                "Latitude phải nằm trong khoảng -90 đến 90."
            )

        if not -180 <= longitude_value <= 180:
            raise ValueError(
                "Longitude phải nằm trong khoảng -180 đến 180."
            )

        return latitude_value, longitude_value

    def _build_params(
        self,
        latitude: float,
        longitude: float,
        forecast_hours: int,
        timezone_name: str,
        domain: str,
    ) -> dict[str, Any]:
        if not isinstance(forecast_hours, int):
            raise TypeError(
                "forecast_hours phải là số nguyên."
            )

        if forecast_hours <= 0:
            raise ValueError(
                "forecast_hours phải lớn hơn 0."
            )

        if not timezone_name.strip():
            raise ValueError(
                "timezone_name không được rỗng."
            )

        if not domain.strip():
            raise ValueError(
                "domain không được rỗng."
            )

        return {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(
                self.hourly_variables
            ),
            "timezone": timezone_name,
            "forecast_hours": forecast_hours,
            "domains": domain,
        }

    @staticmethod
    def _read_error_reason(
        response: requests.Response,
    ) -> str:
        try:
            response_body = response.json()
        except ValueError:
            response_text = response.text.strip()

            return (
                response_text
                or "API không trả nội dung lỗi."
            )

        if isinstance(response_body, dict):
            reason = (
                response_body.get("reason")
                or response_body.get("message")
            )

            if reason:
                return str(reason)

        return str(response_body)

    @retry(
        retry=retry_if_exception_type(
            (
                requests.Timeout,
                requests.ConnectionError,
                RetryableOpenMeteoError,
            )
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(
            multiplier=1,
            min=2,
            max=10,
        ),
        reraise=True,
    )
    def _send_request(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = self.session.get(
                self.base_url,
                params=params,
                timeout=self.timeout_seconds,
            )
        except (
            requests.Timeout,
            requests.ConnectionError,
        ):
            raise
        except requests.RequestException as error:
            raise OpenMeteoClientError(
                "Không thể gửi request đến Open-Meteo."
            ) from error

        if (
            response.status_code
            in RETRYABLE_HTTP_STATUS_CODES
        ):
            reason = self._read_error_reason(
                response
            )

            raise RetryableOpenMeteoError(
                "Open-Meteo gặp lỗi tạm thời. "
                f"HTTP {response.status_code}: {reason}"
            )

        if response.status_code >= 400:
            reason = self._read_error_reason(
                response
            )

            raise OpenMeteoClientError(
                "Open-Meteo từ chối request. "
                f"HTTP {response.status_code}: {reason}"
            )

        try:
            response_data = response.json()
        except ValueError as error:
            raise InvalidOpenMeteoResponseError(
                "Open-Meteo không trả JSON hợp lệ."
            ) from error

        if not isinstance(response_data, dict):
            raise InvalidOpenMeteoResponseError(
                "Response của một điểm phải là JSON object."
            )

        if response_data.get("error") is True:
            reason = response_data.get(
                "reason",
                "Không rõ nguyên nhân.",
            )

            raise OpenMeteoClientError(
                f"Open-Meteo báo lỗi: {reason}"
            )

        return response_data

    def _validate_response(
        self,
        response_data: dict[str, Any],
    ) -> None:
        hourly_data = response_data.get("hourly")
        hourly_units = response_data.get(
            "hourly_units"
        )

        if not isinstance(hourly_data, dict):
            raise InvalidOpenMeteoResponseError(
                "Response thiếu object 'hourly'."
            )

        if not isinstance(hourly_units, dict):
            raise InvalidOpenMeteoResponseError(
                "Response thiếu object 'hourly_units'."
            )

        required_hourly_fields = {
            "time",
            *self.hourly_variables,
        }

        missing_fields = (
            required_hourly_fields
            - set(hourly_data)
        )

        if missing_fields:
            missing_text = ", ".join(
                sorted(missing_fields)
            )

            raise InvalidOpenMeteoResponseError(
                "Object 'hourly' thiếu trường: "
                f"{missing_text}"
            )

        time_values = hourly_data["time"]

        if not isinstance(time_values, list):
            raise InvalidOpenMeteoResponseError(
                "hourly.time phải là một array."
            )

        if not time_values:
            raise InvalidOpenMeteoResponseError(
                "hourly.time không có dữ liệu."
            )

        expected_length = len(time_values)

        for variable in self.hourly_variables:
            values = hourly_data[variable]

            if not isinstance(values, list):
                raise InvalidOpenMeteoResponseError(
                    f"hourly.{variable} phải là array."
                )

            if len(values) != expected_length:
                raise InvalidOpenMeteoResponseError(
                    f"hourly.{variable} có "
                    f"{len(values)} phần tử, "
                    f"nhưng hourly.time có "
                    f"{expected_length} phần tử."
                )

            if variable not in hourly_units:
                raise InvalidOpenMeteoResponseError(
                    "hourly_units thiếu đơn vị của "
                    f"'{variable}'."
                )

    def fetch_hourly_air_quality(
        self,
        point_id: str,
        location_id: str,
        latitude: float,
        longitude: float,
        forecast_hours: int = 24,
        timezone_name: str = "Asia/Ho_Chi_Minh",
        domain: str = "cams_global",
    ) -> dict[str, Any]:
        cleaned_point_id = self._validate_identifier(
            point_id,
            "point_id",
        )

        cleaned_location_id = (
            self._validate_identifier(
                location_id,
                "location_id",
            )
        )

        (
            latitude_value,
            longitude_value,
        ) = self._validate_coordinates(
            latitude,
            longitude,
        )

        params = self._build_params(
            latitude=latitude_value,
            longitude=longitude_value,
            forecast_hours=forecast_hours,
            timezone_name=timezone_name,
            domain=domain,
        )

        try:
            response_data = self._send_request(
                params=params
            )
        except (
            requests.Timeout,
            requests.ConnectionError,
        ) as error:
            raise OpenMeteoClientError(
                "Không thể kết nối đến Open-Meteo "
                "sau các lần retry."
            ) from error

        self._validate_response(
            response_data=response_data
        )

        return {
            "schema_version": "1.0",
            "source": "open_meteo",
            "ingested_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "request": {
                "point_id": cleaned_point_id,
                "location_id": cleaned_location_id,
                "latitude": latitude_value,
                "longitude": longitude_value,
                "forecast_hours": forecast_hours,
                "timezone": timezone_name,
                "domain": domain,
                "hourly_variables": list(
                    self.hourly_variables
                ),
            },
            "response": response_data,
        }

    def close(self) -> None:
        self.session.close()