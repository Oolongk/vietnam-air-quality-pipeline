from __future__ import annotations

import re
from typing import Any

import requests

SAFE_RELEASE_PREFIX_PATTERN = re.compile(r"^releases/[A-Za-z0-9_-]+$")

SAFE_POINT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class AirQualitySnapshotError(RuntimeError):
    """
    Lỗi khi Dashboard đọc public snapshot.
    """


class AirQualitySnapshotClient:
    """
    Client đọc JSON snapshot thông qua
    Lambda Function URL hoặc CloudFront.

    Client không biết lớp public access đang là
    Lambda hay CloudFront. Nó chỉ cần một base URL.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: int = 20,
    ) -> None:
        normalized_url = base_url.strip().rstrip("/")

        if not normalized_url:
            raise ValueError("Public snapshot base URL không được rỗng.")

        if not normalized_url.startswith(
            (
                "https://",
                "http://",
            )
        ):
            raise ValueError(
                "Public snapshot base URL phải bắt đầu bằng http:// hoặc https://."
            )

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds phải lớn hơn 0.")

        self.base_url = normalized_url
        self.timeout_seconds = timeout_seconds

    def _get_json_url(
        self,
        url: str,
    ) -> dict[str, Any]:
        try:
            response = requests.get(
                url=url,
                headers={
                    "Accept": "application/json",
                },
                timeout=self.timeout_seconds,
            )

        except requests.RequestException as error:
            raise AirQualitySnapshotError(
                f"Không kết nối được public snapshot tại {url}: {error}"
            ) from error

        if not response.ok:
            detail: Any

            try:
                error_payload = response.json()

                if isinstance(
                    error_payload,
                    dict,
                ):
                    detail = error_payload.get(
                        "error",
                        error_payload,
                    )

                else:
                    detail = error_payload

            except ValueError:
                detail = response.text.strip() or response.reason

            raise AirQualitySnapshotError(
                f"Public snapshot trả lỗi {response.status_code}: {detail}"
            )

        try:
            payload = response.json()

        except ValueError as error:
            raise AirQualitySnapshotError(
                "Public snapshot không trả về JSON hợp lệ."
            ) from error

        if not isinstance(
            payload,
            dict,
        ):
            raise AirQualitySnapshotError("Phản hồi snapshot phải là một JSON object.")

        return payload

    def _get_root_file(
        self,
        relative_path: str,
    ) -> dict[str, Any]:
        normalized_path = relative_path.replace(
            "\\",
            "/",
        ).strip("/")

        if not normalized_path or ".." in normalized_path:
            raise AirQualitySnapshotError("Đường dẫn root snapshot không hợp lệ.")

        return self._get_json_url(f"{self.base_url}/{normalized_path}")

    def get_current_pointer(
        self,
    ) -> dict[str, Any]:
        pointer = self._get_root_file("current.json")

        required_fields = {
            "schema_version",
            "snapshot_id",
            "release_prefix",
            "manifest_key",
        }

        missing_fields = sorted(required_fields - set(pointer))

        if missing_fields:
            raise AirQualitySnapshotError(
                "current.json thiếu field: " + ", ".join(missing_fields)
            )

        release_prefix = pointer.get("release_prefix")

        if not isinstance(
            release_prefix,
            str,
        ):
            raise AirQualitySnapshotError(
                "release_prefix trong current.json phải là string."
            )

        release_prefix = release_prefix.strip("/")

        if not SAFE_RELEASE_PREFIX_PATTERN.fullmatch(release_prefix):
            raise AirQualitySnapshotError(
                "release_prefix trong current.json không hợp lệ."
            )

        return pointer

    def _get_release_file(
        self,
        relative_path: str,
    ) -> dict[str, Any]:
        normalized_path = relative_path.replace(
            "\\",
            "/",
        ).strip("/")

        if (
            not normalized_path
            or ".." in normalized_path
            or not normalized_path.endswith(".json")
        ):
            raise AirQualitySnapshotError("Đường dẫn release snapshot không hợp lệ.")

        pointer = self.get_current_pointer()

        release_prefix = str(pointer["release_prefix"]).strip("/")

        url = f"{self.base_url}/{release_prefix}/{normalized_path}"

        return self._get_json_url(url)

    @staticmethod
    def _apply_record_limit(
        payload: dict[str, Any],
        limit: int,
    ) -> dict[str, Any]:
        if limit <= 0:
            raise ValueError("limit phải lớn hơn 0.")

        data = payload.get("data")

        if not isinstance(
            data,
            list,
        ):
            return payload

        limited_data = data[:limit]

        limited_payload = dict(payload)

        limited_payload["data"] = limited_data

        limited_payload["record_count"] = len(limited_data)

        return limited_payload

    def get_health(
        self,
    ) -> dict[str, Any]:
        return self._get_release_file("health.json")

    def get_latest_air_quality(
        self,
        limit: int = 5000,
    ) -> dict[str, Any]:
        payload = self._get_release_file("air_quality/latest.json")

        return self._apply_record_limit(
            payload=payload,
            limit=limit,
        )

    def get_point_history(
        self,
        point_id: str,
        limit: int = 720,
    ) -> dict[str, Any]:
        normalized_point_id = point_id.strip().upper()

        if not SAFE_POINT_ID_PATTERN.fullmatch(normalized_point_id):
            raise AirQualitySnapshotError("point_id không hợp lệ.")

        payload = self._get_release_file(
            (f"air_quality/history/{normalized_point_id}.json")
        )

        return self._apply_record_limit(
            payload=payload,
            limit=limit,
        )

    def get_latest_alerts(
        self,
        limit: int = 100,
    ) -> dict[str, Any]:
        payload = self._get_release_file("alerts/latest.json")

        return self._apply_record_limit(
            payload=payload,
            limit=limit,
        )

    def get_pipeline_health(
        self,
    ) -> dict[str, Any]:
        return self._get_release_file("pipeline/health.json")

    def get_data_quality(
        self,
    ) -> dict[str, Any]:
        return self._get_release_file("data_quality/latest.json")
