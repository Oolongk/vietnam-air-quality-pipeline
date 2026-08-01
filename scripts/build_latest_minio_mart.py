from __future__ import annotations

import json

from dotenv import load_dotenv

from src.mart.minio_air_quality_mart_builder import (
    build_latest_minio_mart,
)
from src.operations.batch_context import PipelineBatchContext
from src.quality.minio_quality_processor import (
    load_loadable_quality_batch_for_context,
)


def main() -> None:
    load_dotenv()

    batch_context = PipelineBatchContext.from_environment()

    if batch_context is None:
        summary = build_latest_minio_mart()
    else:
        _, quality_summary = load_loadable_quality_batch_for_context(batch_context)
        summary = build_latest_minio_mart(
            source_clean_object_name=quality_summary["clean_object_name"],
            expected_batch_id=batch_context.batch_id,
        )
        batch_context.validate_summary(summary, "Mart summary")

    print()
    execution_mode = "AIRFLOW_BATCH" if batch_context is not None else "LATEST_MANUAL"
    print(f"Execution mode: {execution_mode}")
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
