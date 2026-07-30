from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.parse import unquote

import boto3
from botocore.exceptions import BotoCoreError, ClientError

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)


SNAPSHOT_BUCKET = os.getenv(
    "SNAPSHOT_BUCKET",
    "",
).strip()

SNAPSHOT_REGION = os.getenv(
    "SNAPSHOT_REGION",
    os.getenv(
        "AWS_REGION",
        "ap-southeast-2",
    ),
).strip()


MAX_RESPONSE_BYTES = 5 * 1024 * 1024

SAFE_SNAPSHOT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

SAFE_OBJECT_PATH_PATTERN = re.compile(r"^[A-Za-z0-9_./-]+$")


S3_CLIENT = boto3.client(
    "s3",
    region_name=SNAPSHOT_REGION,
)


def lambda_handler(
    event: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    """
    Đọc JSON snapshot từ private S3 và trả qua
    Lambda Function URL.

    Chỉ hỗ trợ GET và HEAD.
    """

    if not SNAPSHOT_BUCKET:
        LOGGER.error("Missing SNAPSHOT_BUCKET environment variable.")

        return build_error_response(
            status_code=500,
            message="Snapshot service is not configured.",
        )

    method = extract_http_method(event)

    if method not in {
        "GET",
        "HEAD",
    }:
        return {
            "statusCode": 405,
            "headers": {
                **base_headers(),
                "allow": "GET, HEAD",
                "cache-control": "no-store",
            },
            "body": json.dumps(
                {
                    "error": "Method not allowed.",
                }
            ),
        }

    raw_path = extract_raw_path(event)

    object_key = normalize_object_key(raw_path)

    if object_key is None or not is_allowed_object_key(object_key):
        return build_error_response(
            status_code=404,
            message="Snapshot file not found.",
        )

    try:
        if method == "HEAD":
            return read_object_metadata(object_key)

        return read_object_body(object_key)

    except ClientError as error:
        error_code = str(
            error.response.get(
                "Error",
                {},
            ).get(
                "Code",
                "",
            )
        )

        if error_code in {
            "404",
            "NoSuchKey",
            "NotFound",
        }:
            return build_error_response(
                status_code=404,
                message="Snapshot file not found.",
            )

        LOGGER.exception(
            "S3 ClientError while reading key=%s, code=%s",
            object_key,
            error_code,
        )

        return build_error_response(
            status_code=500,
            message="Snapshot file is temporarily unavailable.",
        )

    except (
        BotoCoreError,
        UnicodeDecodeError,
        OSError,
    ):
        LOGGER.exception(
            "Unexpected object read error for key=%s",
            object_key,
        )

        return build_error_response(
            status_code=500,
            message="Snapshot file is temporarily unavailable.",
        )


def extract_http_method(
    event: dict[str, Any],
) -> str:
    request_context = event.get(
        "requestContext",
        {},
    )

    http_context = request_context.get(
        "http",
        {},
    )

    method = http_context.get(
        "method",
        "",
    )

    return str(method).upper().strip()


def extract_raw_path(
    event: dict[str, Any],
) -> str:
    raw_path = event.get("rawPath")

    if isinstance(
        raw_path,
        str,
    ):
        return raw_path

    request_context = event.get(
        "requestContext",
        {},
    )

    http_context = request_context.get(
        "http",
        {},
    )

    fallback_path = http_context.get(
        "path",
        "/",
    )

    return str(fallback_path)


def normalize_object_key(
    raw_path: str,
) -> str | None:
    """
    Chuyển URL path thành S3 object key.

    Ví dụ:
    /current.json
    → current.json
    """

    try:
        decoded_path = unquote(raw_path)

    except Exception:
        return None

    if "\x00" in decoded_path:
        return None

    normalized_path = decoded_path.replace(
        "\\",
        "/",
    ).strip()

    if not normalized_path.startswith("/"):
        return None

    object_key = normalized_path.lstrip("/")

    if not object_key:
        return None

    return object_key


def is_allowed_object_key(
    object_key: str,
) -> bool:
    """
    Chỉ cho phép current.json hoặc JSON nằm
    trong một release hợp lệ.
    """

    if object_key == "current.json":
        return True

    if not object_key.startswith("releases/"):
        return False

    if not object_key.endswith(".json"):
        return False

    if not SAFE_OBJECT_PATH_PATTERN.fullmatch(object_key):
        return False

    path_parts = object_key.split("/")

    if len(path_parts) < 3:
        return False

    if path_parts[0] != "releases":
        return False

    snapshot_id = path_parts[1]

    if not SAFE_SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id):
        return False

    for path_part in path_parts:
        if path_part in {
            "",
            ".",
            "..",
        }:
            return False

    return True


def read_object_body(
    object_key: str,
) -> dict[str, Any]:
    response = S3_CLIENT.get_object(
        Bucket=SNAPSHOT_BUCKET,
        Key=object_key,
    )

    content_length = int(
        response.get(
            "ContentLength",
            0,
        )
        or 0
    )

    if content_length > MAX_RESPONSE_BYTES:
        LOGGER.warning(
            "Object is too large: key=%s, bytes=%s",
            object_key,
            content_length,
        )

        return build_error_response(
            status_code=413,
            message="Snapshot file is too large.",
        )

    body_stream = response["Body"]

    try:
        body_bytes = body_stream.read(MAX_RESPONSE_BYTES + 1)

    finally:
        body_stream.close()

    if len(body_bytes) > MAX_RESPONSE_BYTES:
        return build_error_response(
            status_code=413,
            message="Snapshot file is too large.",
        )

    body_text = body_bytes.decode("utf-8")

    return {
        "statusCode": 200,
        "headers": build_s3_response_headers(
            object_key=object_key,
            s3_response=response,
        ),
        "body": body_text,
        "isBase64Encoded": False,
    }


def read_object_metadata(
    object_key: str,
) -> dict[str, Any]:
    response = S3_CLIENT.head_object(
        Bucket=SNAPSHOT_BUCKET,
        Key=object_key,
    )

    return {
        "statusCode": 200,
        "headers": build_s3_response_headers(
            object_key=object_key,
            s3_response=response,
        ),
        "body": "",
        "isBase64Encoded": False,
    }


def build_s3_response_headers(
    object_key: str,
    s3_response: dict[str, Any],
) -> dict[str, str]:
    content_type = str(
        s3_response.get(
            "ContentType",
            "application/json; charset=utf-8",
        )
    )

    cache_control = s3_response.get("CacheControl")

    if not cache_control:
        if object_key == "current.json":
            cache_control = "max-age=0, no-cache, no-store, must-revalidate"

        else:
            cache_control = "public, max-age=31536000, immutable"

    headers = {
        **base_headers(),
        "content-type": content_type,
        "cache-control": str(cache_control),
    }

    etag = s3_response.get("ETag")

    if etag:
        headers["etag"] = str(etag)

    content_length = s3_response.get("ContentLength")

    if content_length is not None:
        headers["content-length"] = str(content_length)

    return headers


def base_headers() -> dict[str, str]:
    return {
        "x-content-type-options": "nosniff",
        "content-language": "en",
    }


def build_error_response(
    status_code: int,
    message: str,
) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            **base_headers(),
            "content-type": ("application/json; charset=utf-8"),
            "cache-control": "no-store",
        },
        "body": json.dumps(
            {
                "error": message,
            },
            ensure_ascii=False,
        ),
        "isBase64Encoded": False,
    }
