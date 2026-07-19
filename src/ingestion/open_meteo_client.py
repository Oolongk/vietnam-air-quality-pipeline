from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Sequence

import requests
from dotenv import load_dotenv
from tenacity import (
    Retrying,
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


RETRYABLE_HTTP_STATUS_CODES: set[int] = {
    408,
    429,
    500,
    502,
    503,
    504,
}


class OpenMeteoClientError(RuntimeError):
    """Lỗi chung khi giao tiếp với Open-Meteo API."""


class RetryableOpenMeteoError(
    OpenMeteoClientError
):
    """Lỗi tạm thời có thể thử gọi lại."""


class InvalidOpenMeteoResponseError(
    OpenMeteoClientError
):
    """API phản hồi thành công nhưng dữ liệu không hợp lệ."""


def get_int_environment(
    name: str,
    default: int,
) -> int:
    """
    Đọc biến môi trường dạng số nguyên.

    Args:
        name:
            Tên biến môi trường.

        default:
            Giá trị mặc định nếu biến chưa được cấu hình.

    Returns:
        Giá trị số nguyên.

    Raises:
        ValueError:
            Nếu giá trị không thể chuyển thành số nguyên.
    """

    raw_value = os.getenv(
        name,
        str(default),
    ).strip()

    try:
        return int(
            raw_value
        )

    except ValueError as error:
        raise ValueError(
            f"{name} phải là số nguyên, "
            f"nhận được {raw_value!r}."
        ) from error


def get_float_environment(
    name: str,
    default: float,
) -> float:
    """
    Đọc biến môi trường dạng số thực.

    Args:
        name:
            Tên biến môi trường.

        default:
            Giá trị mặc định nếu biến chưa được cấu hình.

    Returns:
        Giá trị số thực.

    Raises:
        ValueError:
            Nếu giá trị không thể chuyển thành số.
    """

    raw_value = os.getenv(
        name,
        str(default),
    ).strip()

    try:
        return float(
            raw_value
        )

    except ValueError as error:
        raise ValueError(
            f"{name} phải là số, "
            f"nhận được {raw_value!r}."
        ) from error


class OpenMeteoClient:
    """
    Client dùng để lấy dữ liệu Air Quality từ Open-Meteo.

    Client hỗ trợ:

    - Gọi một monitoring point.
    - Gọi nhiều monitoring point trong một request.
    - Connect timeout và read timeout riêng.
    - Retry lỗi mạng và lỗi HTTP tạm thời.
    - Exponential backoff.
    - Kiểm tra cấu trúc response.
    - Giữ nguyên Raw JSON contract của pipeline.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        connect_timeout_seconds: float | None = None,
        read_timeout_seconds: float | None = None,
        hourly_variables: Sequence[str] | None = None,
        max_attempts: int | None = None,
        backoff_multiplier: float | None = None,
        backoff_min_seconds: float | None = None,
        backoff_max_seconds: float | None = None,
    ) -> None:
        """
        Khởi tạo Open-Meteo client.

        `timeout_seconds` được giữ lại để tương thích code cũ.
        Nếu truyền `timeout_seconds`, giá trị đó sẽ được dùng cho
        cả connect timeout và read timeout, trừ khi hai timeout
        riêng được truyền trực tiếp.
        """

        load_dotenv()

        configured_url = (
            base_url
            or os.getenv(
                "OPEN_METEO_AIR_QUALITY_URL"
            )
        )

        if not configured_url:
            raise OpenMeteoClientError(
                "Chưa cấu hình "
                "OPEN_METEO_AIR_QUALITY_URL."
            )

        selected_variables = tuple(
            hourly_variables
            or DEFAULT_HOURLY_VARIABLES
        )

        if not selected_variables:
            raise ValueError(
                "Danh sách hourly_variables "
                "không được rỗng."
            )

        legacy_timeout = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else None
        )

        configured_connect_timeout = (
            connect_timeout_seconds
            if connect_timeout_seconds is not None
            else (
                legacy_timeout
                if legacy_timeout is not None
                else get_float_environment(
                    "OPEN_METEO_CONNECT_TIMEOUT_SECONDS",
                    10.0,
                )
            )
        )

        configured_read_timeout = (
            read_timeout_seconds
            if read_timeout_seconds is not None
            else (
                legacy_timeout
                if legacy_timeout is not None
                else get_float_environment(
                    "OPEN_METEO_READ_TIMEOUT_SECONDS",
                    60.0,
                )
            )
        )

        configured_max_attempts = (
            max_attempts
            if max_attempts is not None
            else get_int_environment(
                "OPEN_METEO_MAX_ATTEMPTS",
                3,
            )
        )

        configured_backoff_multiplier = (
            backoff_multiplier
            if backoff_multiplier is not None
            else get_float_environment(
                "OPEN_METEO_BACKOFF_MULTIPLIER",
                1.0,
            )
        )

        configured_backoff_min = (
            backoff_min_seconds
            if backoff_min_seconds is not None
            else get_float_environment(
                "OPEN_METEO_BACKOFF_MIN_SECONDS",
                2.0,
            )
        )

        configured_backoff_max = (
            backoff_max_seconds
            if backoff_max_seconds is not None
            else get_float_environment(
                "OPEN_METEO_BACKOFF_MAX_SECONDS",
                30.0,
            )
        )

        if configured_connect_timeout <= 0:
            raise ValueError(
                "connect_timeout_seconds "
                "phải lớn hơn 0."
            )

        if configured_read_timeout <= 0:
            raise ValueError(
                "read_timeout_seconds "
                "phải lớn hơn 0."
            )

        if configured_max_attempts <= 0:
            raise ValueError(
                "max_attempts phải lớn hơn 0."
            )

        if configured_backoff_multiplier < 0:
            raise ValueError(
                "backoff_multiplier "
                "không được nhỏ hơn 0."
            )

        if configured_backoff_min < 0:
            raise ValueError(
                "backoff_min_seconds "
                "không được nhỏ hơn 0."
            )

        if configured_backoff_max < 0:
            raise ValueError(
                "backoff_max_seconds "
                "không được nhỏ hơn 0."
            )

        if (
            configured_backoff_max
            < configured_backoff_min
        ):
            raise ValueError(
                "backoff_max_seconds không được "
                "nhỏ hơn backoff_min_seconds."
            )

        self.base_url = (
            configured_url.rstrip(
                "/"
            )
        )

        self.hourly_variables = (
            selected_variables
        )

        self.connect_timeout_seconds = float(
            configured_connect_timeout
        )

        self.read_timeout_seconds = float(
            configured_read_timeout
        )

        self.max_attempts = int(
            configured_max_attempts
        )

        self.backoff_multiplier = float(
            configured_backoff_multiplier
        )

        self.backoff_min_seconds = float(
            configured_backoff_min
        )

        self.backoff_max_seconds = float(
            configured_backoff_max
        )

        self.session = requests.Session()

        self.session.headers.update(
            {
                "User-Agent": (
                    "vietnam-air-quality-pipeline/1.0"
                ),
                "Accept": "application/json",
            }
        )

        # Số HTTP request thật, bao gồm cả các lần retry.
        self.total_http_attempts = 0

        # Số attempt của request gần nhất.
        self.last_request_attempts = 0

    @staticmethod
    def _validate_identifier(
        value: str,
        field_name: str,
    ) -> str:
        """
        Kiểm tra một identifier như point_id hoặc location_id.
        """

        if not isinstance(
            value,
            str,
        ):
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
        """
        Chuẩn hóa và kiểm tra latitude, longitude.
        """

        try:
            latitude_value = float(
                latitude
            )

            longitude_value = float(
                longitude
            )

        except (
            TypeError,
            ValueError,
        ) as error:
            raise ValueError(
                "Latitude và longitude "
                "phải là số."
            ) from error

        if not -90 <= latitude_value <= 90:
            raise ValueError(
                "Latitude phải nằm trong "
                "khoảng -90 đến 90."
            )

        if not -180 <= longitude_value <= 180:
            raise ValueError(
                "Longitude phải nằm trong "
                "khoảng -180 đến 180."
            )

        return (
            latitude_value,
            longitude_value,
        )

    @staticmethod
    def _validate_request_options(
        forecast_hours: int,
        timezone_name: str,
        domain: str,
    ) -> tuple[int, str, str]:
        """
        Kiểm tra các tham số chung của request.
        """

        if not isinstance(
            forecast_hours,
            int,
        ):
            raise TypeError(
                "forecast_hours "
                "phải là số nguyên."
            )

        if forecast_hours <= 0:
            raise ValueError(
                "forecast_hours "
                "phải lớn hơn 0."
            )

        if not isinstance(
            timezone_name,
            str,
        ):
            raise TypeError(
                "timezone_name phải là chuỗi."
            )

        cleaned_timezone = (
            timezone_name.strip()
        )

        if not cleaned_timezone:
            raise ValueError(
                "timezone_name không được rỗng."
            )

        if not isinstance(
            domain,
            str,
        ):
            raise TypeError(
                "domain phải là chuỗi."
            )

        cleaned_domain = domain.strip()

        if not cleaned_domain:
            raise ValueError(
                "domain không được rỗng."
            )

        return (
            forecast_hours,
            cleaned_timezone,
            cleaned_domain,
        )

    def _build_single_params(
        self,
        latitude: float,
        longitude: float,
        forecast_hours: int,
        timezone_name: str,
        domain: str,
    ) -> dict[str, Any]:
        """
        Tạo query parameters cho một monitoring point.
        """

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

    def _build_batch_params(
        self,
        monitoring_points: Sequence[
            dict[str, Any]
        ],
        forecast_hours: int,
        timezone_name: str,
        domain: str,
    ) -> dict[str, Any]:
        """
        Tạo query parameters cho nhiều monitoring point.

        Latitude và longitude được nối bằng dấu phẩy theo
        đúng thứ tự monitoring_points.
        """

        latitudes: list[str] = []
        longitudes: list[str] = []

        for point in monitoring_points:
            latitude_value = float(
                point["latitude"]
            )

            longitude_value = float(
                point["longitude"]
            )

            latitudes.append(
                str(latitude_value)
            )

            longitudes.append(
                str(longitude_value)
            )

        return {
            "latitude": ",".join(
                latitudes
            ),
            "longitude": ",".join(
                longitudes
            ),
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
        """
        Đọc nội dung lỗi do Open-Meteo trả về.
        """

        try:
            response_body = response.json()

        except ValueError:
            response_text = (
                response.text.strip()
            )

            return (
                response_text
                or "API không trả nội dung lỗi."
            )

        if isinstance(
            response_body,
            dict,
        ):
            reason = (
                response_body.get(
                    "reason"
                )
                or response_body.get(
                    "message"
                )
            )

            if reason:
                return str(
                    reason
                )

        return str(
            response_body
        )

    def _send_request_once(
        self,
        params: dict[str, Any],
    ) -> Any:
        """
        Gửi một HTTP request thật.

        Function này chỉ gửi đúng một lần.
        Retry được quản lý bởi `_send_request`.
        """

        self.total_http_attempts += 1

        try:
            response = self.session.get(
                self.base_url,
                params=params,
                timeout=(
                    self.connect_timeout_seconds,
                    self.read_timeout_seconds,
                ),
            )

        except (
            requests.Timeout,
            requests.ConnectionError,
        ):
            raise

        except requests.RequestException as error:
            raise OpenMeteoClientError(
                "Không thể gửi request "
                "đến Open-Meteo."
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
                f"HTTP {response.status_code}: "
                f"{reason}"
            )

        if response.status_code >= 400:
            reason = self._read_error_reason(
                response
            )

            raise OpenMeteoClientError(
                "Open-Meteo từ chối request. "
                f"HTTP {response.status_code}: "
                f"{reason}"
            )

        try:
            response_data = response.json()

        except ValueError as error:
            raise InvalidOpenMeteoResponseError(
                "Open-Meteo không trả "
                "JSON hợp lệ."
            ) from error

        if isinstance(
            response_data,
            dict,
        ):
            if (
                response_data.get(
                    "error"
                )
                is True
            ):
                reason = response_data.get(
                    "reason",
                    "Không rõ nguyên nhân.",
                )

                raise OpenMeteoClientError(
                    "Open-Meteo báo lỗi: "
                    f"{reason}"
                )

            return response_data

        if isinstance(
            response_data,
            list,
        ):
            return response_data

        raise InvalidOpenMeteoResponseError(
            "Open-Meteo trả về kiểu dữ liệu "
            "không hợp lệ. "
            f"Kiểu nhận được: "
            f"{type(response_data).__name__}"
        )

    def _send_request(
        self,
        params: dict[str, Any],
    ) -> Any:
        """
        Gửi request với retry và exponential backoff.
        """

        self.last_request_attempts = 0

        retrying = Retrying(
            retry=retry_if_exception_type(
                (
                    requests.Timeout,
                    requests.ConnectionError,
                    RetryableOpenMeteoError,
                )
            ),
            stop=stop_after_attempt(
                self.max_attempts
            ),
            wait=wait_exponential(
                multiplier=(
                    self.backoff_multiplier
                ),
                min=(
                    self.backoff_min_seconds
                ),
                max=(
                    self.backoff_max_seconds
                ),
            ),
            reraise=True,
        )

        try:
            for attempt in retrying:
                with attempt:
                    self.last_request_attempts = (
                        attempt.retry_state
                        .attempt_number
                    )

                    return self._send_request_once(
                        params=params
                    )

        except (
            requests.Timeout,
            requests.ConnectionError,
            RetryableOpenMeteoError,
        ) as error:
            raise OpenMeteoClientError(
                "Không thể lấy dữ liệu từ "
                "Open-Meteo sau "
                f"{self.max_attempts} lần thử."
            ) from error

        raise OpenMeteoClientError(
            "Request Open-Meteo kết thúc "
            "không xác định."
        )

    def _validate_response(
        self,
        response_data: dict[str, Any],
    ) -> None:
        """
        Kiểm tra response của một monitoring point.
        """

        hourly_data = response_data.get(
            "hourly"
        )

        hourly_units = response_data.get(
            "hourly_units"
        )

        if not isinstance(
            hourly_data,
            dict,
        ):
            raise InvalidOpenMeteoResponseError(
                "Response thiếu object "
                "'hourly'."
            )

        if not isinstance(
            hourly_units,
            dict,
        ):
            raise InvalidOpenMeteoResponseError(
                "Response thiếu object "
                "'hourly_units'."
            )

        required_hourly_fields = {
            "time",
            *self.hourly_variables,
        }

        missing_fields = (
            required_hourly_fields
            - set(
                hourly_data
            )
        )

        if missing_fields:
            missing_text = ", ".join(
                sorted(
                    missing_fields
                )
            )

            raise InvalidOpenMeteoResponseError(
                "Object 'hourly' thiếu trường: "
                f"{missing_text}"
            )

        time_values = hourly_data[
            "time"
        ]

        if not isinstance(
            time_values,
            list,
        ):
            raise InvalidOpenMeteoResponseError(
                "hourly.time phải là array."
            )

        if not time_values:
            raise InvalidOpenMeteoResponseError(
                "hourly.time không có dữ liệu."
            )

        expected_length = len(
            time_values
        )

        for variable in self.hourly_variables:
            values = hourly_data[
                variable
            ]

            if not isinstance(
                values,
                list,
            ):
                raise InvalidOpenMeteoResponseError(
                    f"hourly.{variable} "
                    "phải là array."
                )

            if len(
                values
            ) != expected_length:
                raise InvalidOpenMeteoResponseError(
                    f"hourly.{variable} có "
                    f"{len(values)} phần tử, "
                    "nhưng hourly.time có "
                    f"{expected_length} phần tử."
                )

            if variable not in hourly_units:
                raise InvalidOpenMeteoResponseError(
                    "hourly_units thiếu đơn vị "
                    f"của '{variable}'."
                )

    def _normalize_batch_responses(
        self,
        response_data: Any,
        expected_count: int,
    ) -> list[dict[str, Any]]:
        """
        Chuẩn hóa response batch thành list JSON object.

        Khi request có một tọa độ, Open-Meteo có thể trả dict.
        Khi request có nhiều tọa độ, Open-Meteo trả list.
        """

        if isinstance(
            response_data,
            dict,
        ):
            responses: list[
                dict[str, Any]
            ] = [
                response_data,
            ]

        elif isinstance(
            response_data,
            list,
        ):
            responses = []

            for response_index, item in enumerate(
                response_data
            ):
                if not isinstance(
                    item,
                    dict,
                ):
                    raise (
                        InvalidOpenMeteoResponseError(
                            "Response batch tại index "
                            f"{response_index} "
                            "không phải JSON object."
                        )
                    )

                responses.append(
                    item
                )

        else:
            raise InvalidOpenMeteoResponseError(
                "Response batch không phải "
                "JSON object hoặc array."
            )

        if len(
            responses
        ) != expected_count:
            raise InvalidOpenMeteoResponseError(
                "Số response Open-Meteo "
                "không khớp số monitoring point. "
                f"Expected={expected_count}, "
                f"actual={len(responses)}."
            )

        for response_index, item in enumerate(
            responses
        ):
            if item.get(
                "error"
            ) is True:
                reason = item.get(
                    "reason",
                    "Không rõ nguyên nhân.",
                )

                raise OpenMeteoClientError(
                    "Open-Meteo báo lỗi tại "
                    f"response index {response_index}: "
                    f"{reason}"
                )

        return responses

    def _build_result(
        self,
        point_id: str,
        location_id: str,
        latitude: float,
        longitude: float,
        forecast_hours: int,
        timezone_name: str,
        domain: str,
        response_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Tạo Raw JSON contract cho một monitoring point.

        Cấu trúc này giữ tương thích với pipeline hiện tại.
        """

        return {
            "schema_version": "1.0",
            "source": "open_meteo",
            "ingested_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "request": {
                "point_id": point_id,
                "location_id": location_id,
                "latitude": latitude,
                "longitude": longitude,
                "forecast_hours": (
                    forecast_hours
                ),
                "timezone": timezone_name,
                "domain": domain,
                "hourly_variables": list(
                    self.hourly_variables
                ),
            },
            "response": response_data,
        }

    def fetch_hourly_air_quality_batch(
        self,
        monitoring_points: Sequence[
            dict[str, Any]
        ],
        forecast_hours: int = 24,
        timezone_name: str = (
            "Asia/Ho_Chi_Minh"
        ),
        domain: str = "cams_global",
    ) -> list[dict[str, Any]]:
        """
        Lấy dữ liệu nhiều monitoring point trong một request.

        Mỗi phần tử đầu vào cần có:

        - point_id
        - location_id
        - latitude
        - longitude

        Kết quả trả về là một list Raw JSON payload.
        Mỗi payload có cùng cấu trúc với method đơn điểm.
        """

        if not monitoring_points:
            return []

        (
            validated_forecast_hours,
            cleaned_timezone_name,
            cleaned_domain,
        ) = self._validate_request_options(
            forecast_hours=forecast_hours,
            timezone_name=timezone_name,
            domain=domain,
        )

        validated_points: list[
            dict[str, Any]
        ] = []

        for point_index, point in enumerate(
            monitoring_points
        ):
            if not isinstance(
                point,
                dict,
            ):
                raise TypeError(
                    "Monitoring point tại index "
                    f"{point_index} phải là dict."
                )

            try:
                point_id = (
                    self._validate_identifier(
                        point["point_id"],
                        "point_id",
                    )
                )

                location_id = (
                    self._validate_identifier(
                        point["location_id"],
                        "location_id",
                    )
                )

                (
                    latitude_value,
                    longitude_value,
                ) = self._validate_coordinates(
                    point["latitude"],
                    point["longitude"],
                )

            except KeyError as error:
                missing_field = str(
                    error.args[0]
                )

                raise ValueError(
                    "Monitoring point tại index "
                    f"{point_index} thiếu field "
                    f"{missing_field!r}."
                ) from error

            validated_points.append(
                {
                    "point_id": point_id,
                    "location_id": location_id,
                    "latitude": latitude_value,
                    "longitude": longitude_value,
                }
            )

        params = self._build_batch_params(
            monitoring_points=(
                validated_points
            ),
            forecast_hours=(
                validated_forecast_hours
            ),
            timezone_name=(
                cleaned_timezone_name
            ),
            domain=cleaned_domain,
        )

        response_data = self._send_request(
            params=params
        )

        responses = (
            self._normalize_batch_responses(
                response_data=response_data,
                expected_count=len(
                    validated_points
                ),
            )
        )

        results: list[
            dict[str, Any]
        ] = []

        for point, response_item in zip(
            validated_points,
            responses,
            strict=True,
        ):
            self._validate_response(
                response_data=response_item
            )

            result = self._build_result(
                point_id=point[
                    "point_id"
                ],
                location_id=point[
                    "location_id"
                ],
                latitude=point[
                    "latitude"
                ],
                longitude=point[
                    "longitude"
                ],
                forecast_hours=(
                    validated_forecast_hours
                ),
                timezone_name=(
                    cleaned_timezone_name
                ),
                domain=cleaned_domain,
                response_data=response_item,
            )

            results.append(
                result
            )

        return results

    def fetch_hourly_air_quality(
        self,
        point_id: str,
        location_id: str,
        latitude: float,
        longitude: float,
        forecast_hours: int = 24,
        timezone_name: str = (
            "Asia/Ho_Chi_Minh"
        ),
        domain: str = "cams_global",
    ) -> dict[str, Any]:
        """
        Lấy dữ liệu cho một monitoring point.

        Method này được giữ nguyên signature để tương thích
        với các script và test đã có từ trước.
        """

        results = (
            self.fetch_hourly_air_quality_batch(
                monitoring_points=[
                    {
                        "point_id": point_id,
                        "location_id": (
                            location_id
                        ),
                        "latitude": latitude,
                        "longitude": longitude,
                    }
                ],
                forecast_hours=forecast_hours,
                timezone_name=timezone_name,
                domain=domain,
            )
        )

        return results[
            0
        ]

    def get_request_metrics(
        self,
    ) -> dict[str, int]:
        """
        Trả metrics HTTP hiện tại của client.
        """

        return {
            "total_http_attempts": (
                self.total_http_attempts
            ),
            "last_request_attempts": (
                self.last_request_attempts
            ),
        }

    def close(
        self,
    ) -> None:
        """Đóng requests session."""

        self.session.close()

    def __enter__(
        self,
    ) -> "OpenMeteoClient":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        self.close()