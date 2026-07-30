from __future__ import annotations

import os
import sys

LEGACY_ENABLE_ENVIRONMENT = "ALLOW_LEGACY_LOCAL_PIPELINE"


def legacy_local_pipeline_enabled() -> bool:
    value = os.getenv(
        LEGACY_ENABLE_ENVIRONMENT,
        "false",
    )
    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def require_legacy_local_pipeline_enabled(
    entrypoint: str,
) -> None:
    """Prevent accidental execution of the superseded local-lake pipeline."""

    if legacy_local_pipeline_enabled():
        return

    print(
        f"Legacy local-lake pipeline entrypoint is disabled: {entrypoint}",
        file=sys.stderr,
    )
    print(
        "Use the active MinIO/Airflow pipeline instead. "
        f"For a deliberate recovery run, set "
        f"{LEGACY_ENABLE_ENVIRONMENT}=true.",
        file=sys.stderr,
    )
    raise SystemExit(2)
