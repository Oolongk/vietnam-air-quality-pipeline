from __future__ import annotations

from typing import Any

import requests


class AirQualityAPIError(
    RuntimeError
):
    """Lỗi khi Dashboard gọi FastAPI."""


class AirQualityAPIClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: int = 20,
    ) -> None:
        normalized_url = (
            base_url.strip().rstrip("/")
        )

        if not normalized_url:
            raise ValueError(
                "API base URL không được rỗng."
            )

        self.base_url = normalized_url
        self.timeout_seconds = (
            timeout_seconds
        )

    def _get(
        self,
        path: str,
        parameters: dict[
            str,
            Any,
        ] | None = None,
    ) -> dict[str, Any]:
        url = (
            f"{self.base_url}{path}"
        )

        try:
            response = requests.get(
                url=url,
                params=parameters,
                timeout=self.timeout_seconds,
            )

        except requests.RequestException as error:
            raise AirQualityAPIError(
                "Không kết nối được FastAPI tại "
                f"{url}: {error}"
            ) from error

        if not response.ok:
            try:
                error_payload = response.json()
                detail = error_payload.get(
                    "detail",
                    error_payload,
                )

            except ValueError:
                detail = response.text

            raise AirQualityAPIError(
                "FastAPI trả lỗi "
                f"{response.status_code}: "
                f"{detail}"
            )

        try:
            payload = response.json()

        except ValueError as error:
            raise AirQualityAPIError(
                "FastAPI không trả về JSON hợp lệ."
            ) from error

        if not isinstance(
            payload,
            dict,
        ):
            raise AirQualityAPIError(
                "Phản hồi API phải là JSON object."
            )

        return payload

    def get_health(
        self,
    ) -> dict[str, Any]:
        return self._get(
            "/health"
        )

    def get_latest_air_quality(
        self,
        limit: int = 2000,
    ) -> dict[str, Any]:
        return self._get(
            "/api/v1/air-quality/latest",
            parameters={
                "limit": limit,
            },
        )

    def get_point_history(
        self,
        point_id: str,
        limit: int = 168,
    ) -> dict[str, Any]:
        normalized_point_id = (
            point_id.strip().upper()
        )

        return self._get(
            (
                "/api/v1/air-quality/"
                f"points/{normalized_point_id}"
            ),
            parameters={
                "limit": limit,
            },
        )

    def get_latest_alerts(
        self,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._get(
            "/api/v1/alerts/latest",
            parameters={
                "limit": limit,
            },
        )

    def get_pipeline_health(
        self,
    ) -> dict[str, Any]:
        return self._get(
            (
                "/api/v1/pipeline/"
                "health/latest"
            )
        )

    def get_data_quality(
        self,
    ) -> dict[str, Any]:
        return self._get(
            "/api/v1/data-quality/latest"
        )