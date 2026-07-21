from __future__ import annotations

import json

from dotenv import load_dotenv

from src.mart.minio_air_quality_mart_builder import (
    build_latest_minio_mart,
)


def main() -> None:
    load_dotenv()

    summary = build_latest_minio_mart()

    print()
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
