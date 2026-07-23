from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


SAFE_IDENTIFIER_PATTERN = re.compile(
    r"^[A-Za-z0-9_-]+$"
)


class SnapshotConfigurationError(
    ValueError
):
    """Cấu hình Snapshot Publisher không hợp lệ."""


class SnapshotAPIError(
    RuntimeError
):
    """Không thể đọc dữ liệu từ FastAPI."""


class SnapshotValidationError(
    RuntimeError
):
    """Response của FastAPI không đúng contract."""


class SnapshotPublishError(
    RuntimeError
):
    """Không thể tạo hoặc thay thế snapshot."""


@dataclass(
    frozen=True
)
class SnapshotSettings:
    api_base_url: str
    output_directory: Path
    request_timeout_seconds: float

    latest_limit: int
    top_polluted_limit: int
    location_limit: int
    point_limit: int
    history_hours: int
    alerts_limit: int

    @classmethod
    def from_environment(
        cls,
    ) -> "SnapshotSettings":
        load_dotenv()

        api_base_url = (
            os.getenv(
                "SNAPSHOT_API_BASE_URL"
            )
            or os.getenv(
                "API_BASE_URL"
            )
            or "http://127.0.0.1:8000"
        )

        normalized_api_base_url = (
            api_base_url.strip().rstrip("/")
        )

        if not normalized_api_base_url:
            raise SnapshotConfigurationError(
                "SNAPSHOT_API_BASE_URL "
                "không được rỗng."
            )

        if not normalized_api_base_url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            raise SnapshotConfigurationError(
                "SNAPSHOT_API_BASE_URL phải "
                "bắt đầu bằng http:// hoặc "
                "https://."
            )

        output_directory_value = (
            os.getenv(
                "SNAPSHOT_OUTPUT_DIRECTORY",
                "data/public_snapshots",
            )
        )

        output_directory = Path(
            output_directory_value
        ).expanduser()

        if not output_directory.is_absolute():
            output_directory = (
                Path.cwd()
                / output_directory
            )

        return cls(
            api_base_url=(
                normalized_api_base_url
            ),
            output_directory=(
                output_directory.resolve()
            ),
            request_timeout_seconds=(
                _read_positive_float(
                    name=(
                        "SNAPSHOT_REQUEST_"
                        "TIMEOUT_SECONDS"
                    ),
                    default=30.0,
                )
            ),
            latest_limit=(
                _read_bounded_integer(
                    name=(
                        "SNAPSHOT_LATEST_LIMIT"
                    ),
                    default=2000,
                    minimum=1,
                    maximum=2000,
                )
            ),
            top_polluted_limit=(
                _read_bounded_integer(
                    name=(
                        "SNAPSHOT_TOP_"
                        "POLLUTED_LIMIT"
                    ),
                    default=100,
                    minimum=1,
                    maximum=100,
                )
            ),
            location_limit=(
                _read_bounded_integer(
                    name=(
                        "SNAPSHOT_LOCATION_LIMIT"
                    ),
                    default=2000,
                    minimum=1,
                    maximum=2000,
                )
            ),
            point_limit=(
                _read_bounded_integer(
                    name=(
                        "SNAPSHOT_POINT_LIMIT"
                    ),
                    default=168,
                    minimum=1,
                    maximum=168,
                )
            ),
            history_hours=(
                _read_bounded_integer(
                    name=(
                        "SNAPSHOT_HISTORY_HOURS"
                    ),
                    default=168,
                    minimum=1,
                    maximum=2160,
                )
            ),
            alerts_limit=(
                _read_bounded_integer(
                    name=(
                        "SNAPSHOT_ALERTS_LIMIT"
                    ),
                    default=1000,
                    minimum=1,
                    maximum=1000,
                )
            ),
        )


def _read_positive_float(
    name: str,
    default: float,
) -> float:
    raw_value = os.getenv(
        name
    )

    if raw_value is None:
        return default

    try:
        value = float(
            raw_value.strip()
        )

    except ValueError as error:
        raise SnapshotConfigurationError(
            f"{name} phải là số."
        ) from error

    if value <= 0:
        raise SnapshotConfigurationError(
            f"{name} phải lớn hơn 0."
        )

    return value


def _read_bounded_integer(
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = os.getenv(
        name
    )

    if raw_value is None:
        return default

    try:
        value = int(
            raw_value.strip()
        )

    except ValueError as error:
        raise SnapshotConfigurationError(
            f"{name} phải là số nguyên."
        ) from error

    if not minimum <= value <= maximum:
        raise SnapshotConfigurationError(
            f"{name} phải nằm trong khoảng "
            f"{minimum} đến {maximum}."
        )

    return value


def build_http_session(
) -> requests.Session:
    retry_policy = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(
            429,
            500,
            502,
            503,
            504,
        ),
        allowed_methods=frozenset(
            {
                "GET",
            }
        ),
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry_policy
    )

    session = requests.Session()

    session.mount(
        "http://",
        adapter,
    )

    session.mount(
        "https://",
        adapter,
    )

    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": (
                "vietnam-air-quality-"
                "snapshot-publisher/1.0"
            ),
        }
    )

    return session


class SnapshotPublisher:
    def __init__(
        self,
        settings: SnapshotSettings,
        session: requests.Session
        | None = None,
    ) -> None:
        self.settings = settings

        self.session = (
            session
            or build_http_session()
        )

    def publish(
        self,
    ) -> dict[str, Any]:
        staging_directory = (
            self._create_staging_directory()
        )

        try:
            result = self._build_snapshot(
                staging_directory
            )

            self._replace_output_directory(
                staging_directory
            )

        except Exception:
            if staging_directory.exists():
                shutil.rmtree(
                    staging_directory,
                    ignore_errors=True,
                )

            raise

        return {
            **result,
            "output_directory": str(
                self.settings
                .output_directory
            ),
        }

    def _build_snapshot(
        self,
        staging_directory: Path,
    ) -> dict[str, Any]:
        generated_at = datetime.now(
            timezone.utc
        )

        snapshot_id = (
            generated_at.strftime(
                "%Y%m%dT%H%M%SZ"
            )
            + "_"
            + uuid.uuid4().hex[:8]
        )

        generated_files: list[str] = []

        health_payload = self._fetch_json(
            path="/health",
            required_fields=(
                "status",
                "service",
                "database",
                "database_time",
            ),
        )

        self._write_json(
            root_directory=(
                staging_directory
            ),
            relative_path="health.json",
            payload=health_payload,
        )

        generated_files.append(
            "health.json"
        )

        locations_payload = (
            self._fetch_json(
                path=(
                    "/api/v1/locations"
                ),
                required_fields=(
                    "status",
                    "record_count",
                    "data",
                ),
            )
        )

        location_records = (
            self._require_record_list(
                payload=locations_payload,
                endpoint=(
                    "/api/v1/locations"
                ),
            )
        )

        self._write_json(
            root_directory=(
                staging_directory
            ),
            relative_path=(
                "locations.json"
            ),
            payload=locations_payload,
        )

        generated_files.append(
            "locations.json"
        )

        points_payload = (
            self._fetch_json(
                path=(
                    "/api/v1/"
                    "monitoring-points"
                ),
                required_fields=(
                    "status",
                    "record_count",
                    "data",
                ),
            )
        )

        point_records = (
            self._require_record_list(
                payload=points_payload,
                endpoint=(
                    "/api/v1/"
                    "monitoring-points"
                ),
            )
        )

        self._write_json(
            root_directory=(
                staging_directory
            ),
            relative_path=(
                "monitoring_points.json"
            ),
            payload=points_payload,
        )

        generated_files.append(
            "monitoring_points.json"
        )

        latest_payload = (
            self._fetch_json(
                path=(
                    "/api/v1/"
                    "air-quality/latest"
                ),
                parameters={
                    "limit": (
                        self.settings
                        .latest_limit
                    ),
                },
                required_fields=(
                    "status",
                    "batch_id",
                    "record_count",
                    "data",
                ),
            )
        )

        latest_records = (
            self._require_record_list(
                payload=latest_payload,
                endpoint=(
                    "/api/v1/"
                    "air-quality/latest"
                ),
            )
        )

        self._write_json(
            root_directory=(
                staging_directory
            ),
            relative_path=(
                "air_quality/latest.json"
            ),
            payload=latest_payload,
        )

        generated_files.append(
            "air_quality/latest.json"
        )

        top_polluted_payload = (
            self._fetch_json(
                path=(
                    "/api/v1/"
                    "air-quality/"
                    "top-polluted"
                ),
                parameters={
                    "limit": (
                        self.settings
                        .top_polluted_limit
                    ),
                },
                required_fields=(
                    "status",
                    "batch_id",
                    "reference_time",
                    "record_count",
                    "data",
                ),
            )
        )

        top_polluted_records = (
            self._require_record_list(
                payload=(
                    top_polluted_payload
                ),
                endpoint=(
                    "/api/v1/"
                    "air-quality/"
                    "top-polluted"
                ),
            )
        )

        self._write_json(
            root_directory=(
                staging_directory
            ),
            relative_path=(
                "air_quality/"
                "top_polluted.json"
            ),
            payload=(
                top_polluted_payload
            ),
        )

        generated_files.append(
            "air_quality/"
            "top_polluted.json"
        )

        alerts_payload = (
            self._fetch_json(
                path=(
                    "/api/v1/"
                    "alerts/latest"
                ),
                parameters={
                    "limit": (
                        self.settings
                        .alerts_limit
                    ),
                },
                required_fields=(
                    "status",
                    "record_count",
                    "data",
                ),
            )
        )

        alert_records = (
            self._require_record_list(
                payload=alerts_payload,
                endpoint=(
                    "/api/v1/"
                    "alerts/latest"
                ),
            )
        )

        self._write_json(
            root_directory=(
                staging_directory
            ),
            relative_path=(
                "alerts/latest.json"
            ),
            payload=alerts_payload,
        )

        generated_files.append(
            "alerts/latest.json"
        )

        pipeline_payload = (
            self._fetch_json(
                path=(
                    "/api/v1/"
                    "pipeline/health/latest"
                ),
                required_fields=(
                    "status",
                    "batch_id",
                    "stage_count",
                    "data",
                ),
            )
        )

        pipeline_records = (
            self._require_record_list(
                payload=pipeline_payload,
                endpoint=(
                    "/api/v1/"
                    "pipeline/health/latest"
                ),
            )
        )

        self._write_json(
            root_directory=(
                staging_directory
            ),
            relative_path=(
                "pipeline/health.json"
            ),
            payload=pipeline_payload,
        )

        generated_files.append(
            "pipeline/health.json"
        )

        quality_payload = (
            self._fetch_json(
                path=(
                    "/api/v1/"
                    "data-quality/latest"
                ),
                required_fields=(
                    "status",
                    "check_count",
                    "failed_check_count",
                    "data",
                ),
            )
        )

        quality_records = (
            self._require_record_list(
                payload=quality_payload,
                endpoint=(
                    "/api/v1/"
                    "data-quality/latest"
                ),
            )
        )

        self._write_json(
            root_directory=(
                staging_directory
            ),
            relative_path=(
                "data_quality/latest.json"
            ),
            payload=quality_payload,
        )

        generated_files.append(
            "data_quality/latest.json"
        )

        location_ids = (
            self._extract_unique_identifiers(
                records=location_records,
                field_name="location_id",
                endpoint=(
                    "/api/v1/locations"
                ),
            )
        )

        for location_id in location_ids:
            encoded_location_id = quote(
                location_id,
                safe="",
            )

            location_payload = (
                self._fetch_json(
                    path=(
                        "/api/v1/"
                        "air-quality/"
                        "locations/"
                        f"{encoded_location_id}"
                    ),
                    parameters={
                        "limit": (
                            self.settings
                            .location_limit
                        ),
                    },
                    required_fields=(
                        "status",
                        "location_id",
                        "location_name",
                        "batch_id",
                        "record_count",
                        "data",
                    ),
                )
            )

            self._require_record_list(
                payload=location_payload,
                endpoint=(
                    "/api/v1/"
                    "air-quality/"
                    "locations/"
                    f"{location_id}"
                ),
            )

            relative_path = (
                "air_quality/"
                "locations/"
                f"{location_id}.json"
            )

            self._write_json(
                root_directory=(
                    staging_directory
                ),
                relative_path=(
                    relative_path
                ),
                payload=location_payload,
            )

            generated_files.append(
                relative_path
            )

        point_ids = (
            self._extract_unique_identifiers(
                records=point_records,
                field_name="point_id",
                endpoint=(
                    "/api/v1/"
                    "monitoring-points"
                ),
            )
        )

        for point_id in point_ids:
            encoded_point_id = quote(
                point_id,
                safe="",
            )

            point_payload = (
                self._fetch_json(
                    path=(
                        "/api/v1/"
                        "air-quality/"
                        "points/"
                        f"{encoded_point_id}"
                    ),
                    parameters={
                        "limit": (
                            self.settings
                            .point_limit
                        ),
                    },
                    required_fields=(
                        "status",
                        "point_id",
                        "batch_id",
                        "record_count",
                        "data",
                    ),
                )
            )

            self._require_record_list(
                payload=point_payload,
                endpoint=(
                    "/api/v1/"
                    "air-quality/"
                    "points/"
                    f"{point_id}"
                ),
            )

            point_relative_path = (
                "air_quality/"
                "points/"
                f"{point_id}.json"
            )

            self._write_json(
                root_directory=(
                    staging_directory
                ),
                relative_path=(
                    point_relative_path
                ),
                payload=point_payload,
            )

            generated_files.append(
                point_relative_path
            )

            history_payload = (
                self._fetch_json(
                    path=(
                        "/api/v1/"
                        "air-quality/history"
                    ),
                    parameters={
                        "point_id": point_id,
                        "hours": (
                            self.settings
                            .history_hours
                        ),
                    },
                    required_fields=(
                        "status",
                        "point_id",
                        "requested_hours",
                        "record_count",
                        "data",
                    ),
                )
            )

            self._require_record_list(
                payload=history_payload,
                endpoint=(
                    "/api/v1/"
                    "air-quality/history"
                    f"?point_id={point_id}"
                ),
            )

            history_relative_path = (
                "air_quality/"
                "history/"
                f"{point_id}.json"
            )

            self._write_json(
                root_directory=(
                    staging_directory
                ),
                relative_path=(
                    history_relative_path
                ),
                payload=history_payload,
            )

            generated_files.append(
                history_relative_path
            )

        manifest_payload = {
            "schema_version": "1.0",
            "snapshot_id": snapshot_id,
            "generated_at": (
                generated_at.isoformat()
            ),
            "source": {
                "type": "fastapi",
                "base_url": (
                    self.settings
                    .api_base_url
                ),
                "service": (
                    health_payload[
                        "service"
                    ]
                ),
                "database": (
                    health_payload[
                        "database"
                    ]
                ),
            },
            "latest_batch_id": (
                latest_payload.get(
                    "batch_id"
                )
            ),
            "statuses": {
                "api": (
                    health_payload.get(
                        "status"
                    )
                ),
                "pipeline": (
                    pipeline_payload.get(
                        "status"
                    )
                ),
                "data_quality": (
                    quality_payload.get(
                        "status"
                    )
                ),
            },
            "counts": {
                "locations": len(
                    location_records
                ),
                "monitoring_points": len(
                    point_records
                ),
                "latest_air_quality_records": (
                    len(
                        latest_records
                    )
                ),
                "top_polluted_records": (
                    len(
                        top_polluted_records
                    )
                ),
                "alert_records": len(
                    alert_records
                ),
                "pipeline_stages": len(
                    pipeline_records
                ),
                "data_quality_checks": len(
                    quality_records
                ),
                "location_snapshots": len(
                    location_ids
                ),
                "point_snapshots": len(
                    point_ids
                ),
                "history_snapshots": len(
                    point_ids
                ),
            },
            "files": sorted(
                [
                    *generated_files,
                    "manifest.json",
                ]
            ),
        }

        self._write_json(
            root_directory=(
                staging_directory
            ),
            relative_path=(
                "manifest.json"
            ),
            payload=manifest_payload,
        )

        generated_files.append(
            "manifest.json"
        )

        return {
            "status": "SUCCESS",
            "snapshot_id": snapshot_id,
            "generated_at": (
                generated_at.isoformat()
            ),
            "latest_batch_id": (
                latest_payload.get(
                    "batch_id"
                )
            ),
            "file_count": len(
                generated_files
            ),
            "location_count": len(
                location_ids
            ),
            "point_count": len(
                point_ids
            ),
            "manifest": (
                manifest_payload
            ),
        }

    def _fetch_json(
        self,
        path: str,
        parameters: dict[str, Any]
        | None = None,
        required_fields: tuple[
            str,
            ...,
        ] = (),
    ) -> dict[str, Any]:
        normalized_path = (
            "/"
            + path.lstrip("/")
        )

        url = (
            self.settings.api_base_url
            + normalized_path
        )

        try:
            response = self.session.get(
                url=url,
                params=parameters,
                timeout=(
                    self.settings
                    .request_timeout_seconds
                ),
            )

            response.raise_for_status()

        except requests.RequestException as error:
            raise SnapshotAPIError(
                "Không gọi được FastAPI endpoint "
                f"{normalized_path}: {error}"
            ) from error

        try:
            payload = response.json()

        except requests.JSONDecodeError as error:
            raise SnapshotAPIError(
                "FastAPI endpoint không trả "
                "JSON hợp lệ: "
                f"{normalized_path}"
            ) from error

        if not isinstance(
            payload,
            dict,
        ):
            raise SnapshotValidationError(
                "Response phải là JSON object: "
                f"{normalized_path}"
            )

        missing_fields = [
            field_name
            for field_name in required_fields
            if field_name not in payload
        ]

        if missing_fields:
            raise SnapshotValidationError(
                "Response của endpoint "
                f"{normalized_path} thiếu field: "
                + ", ".join(
                    missing_fields
                )
            )

        return payload

    @staticmethod
    def _require_record_list(
        payload: dict[str, Any],
        endpoint: str,
    ) -> list[dict[str, Any]]:
        records = payload.get(
            "data"
        )

        if not isinstance(
            records,
            list,
        ):
            raise SnapshotValidationError(
                "Field data phải là list tại "
                f"endpoint {endpoint}."
            )

        for index, record in enumerate(
            records
        ):
            if not isinstance(
                record,
                dict,
            ):
                raise SnapshotValidationError(
                    "Mỗi phần tử trong data phải "
                    "là JSON object tại endpoint "
                    f"{endpoint}; index={index}."
                )

        return records

    @staticmethod
    def _extract_unique_identifiers(
        records: list[
            dict[str, Any]
        ],
        field_name: str,
        endpoint: str,
    ) -> list[str]:
        identifiers: list[str] = []
        seen_identifiers: set[str] = set()

        for index, record in enumerate(
            records
        ):
            raw_identifier = (
                record.get(
                    field_name
                )
            )

            if not isinstance(
                raw_identifier,
                str,
            ):
                raise SnapshotValidationError(
                    f"{field_name} phải là string "
                    f"tại endpoint {endpoint}; "
                    f"index={index}."
                )

            identifier = (
                raw_identifier.strip()
            )

            if not identifier:
                raise SnapshotValidationError(
                    f"{field_name} không được rỗng "
                    f"tại endpoint {endpoint}; "
                    f"index={index}."
                )

            if not SAFE_IDENTIFIER_PATTERN.fullmatch(
                identifier
            ):
                raise SnapshotValidationError(
                    f"{field_name} không an toàn "
                    "để dùng làm tên file: "
                    f"{identifier!r}."
                )

            if identifier in seen_identifiers:
                raise SnapshotValidationError(
                    f"Trùng {field_name}: "
                    f"{identifier!r} tại endpoint "
                    f"{endpoint}."
                )

            seen_identifiers.add(
                identifier
            )

            identifiers.append(
                identifier
            )

        return sorted(
            identifiers
        )

    @staticmethod
    def _write_json(
        root_directory: Path,
        relative_path: str,
        payload: dict[str, Any],
    ) -> None:
        normalized_relative_path = (
            relative_path
            .replace("\\", "/")
            .strip("/")
        )

        if not normalized_relative_path:
            raise SnapshotPublishError(
                "Đường dẫn JSON không được rỗng."
            )

        if (
            "/../"
            in f"/{normalized_relative_path}/"
        ):
            raise SnapshotPublishError(
                "Đường dẫn JSON không được "
                "chứa '..'."
            )

        target_path = (
            root_directory
            / Path(
                normalized_relative_path
            )
        )

        target_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            with target_path.open(
                mode="w",
                encoding="utf-8",
                newline="\n",
            ) as file_handle:
                json.dump(
                    payload,
                    file_handle,
                    ensure_ascii=False,
                    indent=2,
                )

                file_handle.write(
                    "\n"
                )

        except (
            OSError,
            TypeError,
            ValueError,
        ) as error:
            raise SnapshotPublishError(
                "Không thể ghi JSON file "
                f"{target_path}: {error}"
            ) from error

    def _create_staging_directory(
        self,
    ) -> Path:
        output_directory = (
            self.settings
            .output_directory
        )

        output_directory.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        staging_directory = (
            output_directory.parent
            / (
                f".{output_directory.name}"
                ".staging-"
                f"{uuid.uuid4().hex}"
            )
        )

        try:
            staging_directory.mkdir(
                parents=False,
                exist_ok=False,
            )

        except OSError as error:
            raise SnapshotPublishError(
                "Không thể tạo staging "
                f"directory: {error}"
            ) from error

        return staging_directory

    def _replace_output_directory(
        self,
        staging_directory: Path,
    ) -> None:
        output_directory = (
            self.settings
            .output_directory
        )

        backup_directory = (
            output_directory.parent
            / (
                f".{output_directory.name}"
                ".backup-"
                f"{uuid.uuid4().hex}"
            )
        )

        output_was_backed_up = False

        try:
            if output_directory.exists():
                if not output_directory.is_dir():
                    raise SnapshotPublishError(
                        "Snapshot output path "
                        "đã tồn tại nhưng không "
                        "phải directory: "
                        f"{output_directory}"
                    )

                output_directory.rename(
                    backup_directory
                )

                output_was_backed_up = True

            staging_directory.rename(
                output_directory
            )

        except Exception as error:
            if output_directory.exists():
                shutil.rmtree(
                    output_directory,
                    ignore_errors=True,
                )

            if (
                output_was_backed_up
                and backup_directory.exists()
            ):
                backup_directory.rename(
                    output_directory
                )

            if isinstance(
                error,
                SnapshotPublishError,
            ):
                raise

            raise SnapshotPublishError(
                "Không thể thay thế snapshot "
                f"directory: {error}"
            ) from error

        if backup_directory.exists():
            shutil.rmtree(
                backup_directory,
                ignore_errors=True,
            )


def publish_snapshots(
    settings: SnapshotSettings
    | None = None,
    session: requests.Session
    | None = None,
) -> dict[str, Any]:
    resolved_settings = (
        settings
        or SnapshotSettings.from_environment()
    )

    publisher = SnapshotPublisher(
        settings=resolved_settings,
        session=session,
    )

    return publisher.publish()