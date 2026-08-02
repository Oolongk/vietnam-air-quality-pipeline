from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import unquote


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "configs" / "documentation_book.json"
GENERATED_NOTICE = (
    "<!-- GENERATED FILE: edit source chapters, then run "
    "`python -m scripts.build_unified_documentation` -->"
)
FENCE_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
MARKDOWN_LINK_PATTERN = re.compile(
    r"(?P<prefix>!?\[[^\]]*\]\()(?P<target>[^)\s]+)"
    r"(?P<suffix>(?:\s+['\"][^'\"]*['\"])?\))"
)


class DocumentationBuildError(RuntimeError):
    """Raised when the documentation book cannot be generated safely."""


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DocumentationBuildError(
            f"Không tìm thấy documentation manifest: {path}"
        ) from error
    except json.JSONDecodeError as error:
        raise DocumentationBuildError(
            f"Documentation manifest không phải JSON hợp lệ: {error}"
        ) from error

    chapters = payload.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise DocumentationBuildError(
            "Documentation manifest phải có danh sách chapters không rỗng."
        )

    required = {"id", "part", "title", "source"}
    seen_ids: set[str] = set()
    seen_sources: set[str] = set()

    for index, chapter in enumerate(chapters, start=1):
        if not isinstance(chapter, dict):
            raise DocumentationBuildError(
                f"Chapter {index} phải là object."
            )

        missing = sorted(required - set(chapter))
        if missing:
            raise DocumentationBuildError(
                f"Chapter {index} thiếu trường: {', '.join(missing)}"
            )

        chapter_id = str(chapter["id"]).strip()
        source = str(chapter["source"]).strip()

        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", chapter_id):
            raise DocumentationBuildError(
                f"Chapter id không an toàn: {chapter_id!r}"
            )
        if chapter_id in seen_ids:
            raise DocumentationBuildError(
                f"Chapter id bị trùng: {chapter_id}"
            )
        if source in seen_sources:
            raise DocumentationBuildError(
                f"Chapter source bị trùng: {source}"
            )

        seen_ids.add(chapter_id)
        seen_sources.add(source)

    return payload


def _split_target(target: str) -> tuple[str, str]:
    match = re.match(r"^(?P<path>[^#?]*)(?P<tail>[#?].*)?$", target)
    if match is None:
        return target, ""
    return match.group("path"), match.group("tail") or ""


def _rewrite_link_target(
    target: str,
    *,
    source_path: Path,
    output_path: Path,
) -> str:
    if (
        not target
        or target.startswith(("#", "/", "http://", "https://", "mailto:"))
        or target.startswith("data:")
    ):
        return target

    path_text, tail = _split_target(unquote(target))
    if not path_text:
        return target

    if path_text.startswith("docs/"):
        absolute_target = PROJECT_ROOT / path_text
    else:
        absolute_target = source_path.parent / path_text

    normalized = absolute_target.resolve(strict=False)
    output_parent = output_path.parent.resolve(strict=False)

    try:
        relative = Path(os.path.relpath(normalized, output_parent))
    except ValueError:
        return target

    return relative.as_posix() + tail


def rewrite_relative_links(
    text: str,
    *,
    source_path: Path,
    output_path: Path,
) -> str:
    def replacement(match: re.Match[str]) -> str:
        target = match.group("target")
        rewritten = _rewrite_link_target(
            target,
            source_path=source_path,
            output_path=output_path,
        )
        return (
            match.group("prefix")
            + rewritten
            + match.group("suffix")
        )

    return MARKDOWN_LINK_PATTERN.sub(replacement, text)


def normalize_chapter_markdown(
    text: str,
    *,
    source_path: Path,
    output_path: Path,
) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    first_content_index: int | None = None
    for index, line in enumerate(lines):
        if line.strip():
            first_content_index = index
            break

    if (
        first_content_index is not None
        and re.match(r"^#\s+", lines[first_content_index])
    ):
        lines.pop(first_content_index)

    transformed: list[str] = []
    fence_marker: str | None = None

    for line in lines:
        fence_match = FENCE_PATTERN.match(line)
        if fence_match:
            marker = fence_match.group(1)
            marker_char = marker[0]
            if fence_marker is None:
                fence_marker = marker_char
            elif marker_char == fence_marker:
                fence_marker = None
            transformed.append(line.rstrip())
            continue

        if fence_marker is None:
            heading_match = HEADING_PATTERN.match(line)
            if heading_match:
                hashes = heading_match.group(1)
                title = heading_match.group(2)
                hashes = "#" * min(len(hashes) + 1, 6)
                line = f"{hashes} {title}"

        transformed.append(line.rstrip())

    normalized = "\n".join(transformed).strip()
    return rewrite_relative_links(
        normalized,
        source_path=source_path,
        output_path=output_path,
    )


def _chapter_source_link(
    source_path: Path,
    output_path: Path,
) -> str:
    relative = Path(
        os.path.relpath(
            source_path.resolve(strict=False),
            output_path.parent.resolve(strict=False),
        )
    )
    return relative.as_posix()


def build_book(manifest: dict[str, Any]) -> str:
    output_path = PROJECT_ROOT / str(manifest["output"])
    title = str(manifest["title"]).strip()
    subtitle = str(manifest.get("subtitle", "")).strip()
    chapters = manifest["chapters"]

    lines: list[str] = [
        GENERATED_NOTICE,
        "",
        f"# {title}",
        "",
    ]

    if subtitle:
        lines.extend([subtitle, ""])

    lines.extend(
        [
            "> Đây là bản đọc liên tục được tạo tự động từ các file nguồn "
            "trong `docs/`. Không sửa trực tiếp file này.",
            "",
            "## Mục lục",
            "",
        ]
    )

    current_part: str | None = None
    chapter_number = 0

    for chapter in chapters:
        part = str(chapter["part"]).strip()
        if part != current_part:
            lines.extend([f"### {part}", ""])
            current_part = part

        chapter_number += 1
        lines.append(
            f"{chapter_number}. [{chapter['title']}](#chapter-{chapter['id']})"
        )

    lines.extend(["", "---", ""])
    current_part = None
    chapter_number = 0

    for chapter in chapters:
        part = str(chapter["part"]).strip()
        if part != current_part:
            lines.extend(
                [
                    f"# {part}",
                    "",
                ]
            )
            current_part = part

        chapter_number += 1
        chapter_id = str(chapter["id"])
        chapter_title = str(chapter["title"]).strip()
        source_path = PROJECT_ROOT / str(chapter["source"])

        if not source_path.is_file():
            raise DocumentationBuildError(
                f"Không tìm thấy source chapter: {source_path}"
            )

        source_text = source_path.read_text(encoding="utf-8")
        normalized = normalize_chapter_markdown(
            source_text,
            source_path=source_path,
            output_path=output_path,
        )
        source_link = _chapter_source_link(source_path, output_path)

        lines.extend(
            [
                f'<a id="chapter-{chapter_id}"></a>',
                "",
                f"## Chương {chapter_number} — {chapter_title}",
                "",
                f"*Nguồn: [`{chapter['source']}`]({source_link})*",
                "",
                normalized,
                "",
                "[↑ Về mục lục](#mục-lục)",
                "",
                "---",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def build_landing_page(manifest: dict[str, Any]) -> str:
    title = str(manifest["title"]).strip()
    subtitle = str(manifest.get("subtitle", "")).strip()
    output_path = PROJECT_ROOT / str(manifest["output"])
    landing_path = PROJECT_ROOT / str(manifest["landing_page"])

    book_link = Path(
        os.path.relpath(
            output_path.resolve(strict=False),
            landing_path.parent.resolve(strict=False),
        )
    ).as_posix()

    lines: list[str] = [
        "<!-- GENERATED DOCUMENTATION LANDING PAGE -->",
        "",
        f"# {title}",
        "",
    ]

    if subtitle:
        lines.extend([subtitle, ""])

    lines.extend(
        [
            "## Đọc tài liệu",
            "",
            f"**[Mở toàn bộ tài liệu dưới dạng một bài liên tục]"
            f"({book_link})**",
            "",
            "Các file Markdown riêng vẫn được giữ làm source chapter để dễ "
            "bảo trì và review trên Git.",
            "",
            "## Cấu trúc chương",
            "",
        ]
    )

    current_part: str | None = None
    chapter_number = 0

    for chapter in manifest["chapters"]:
        part = str(chapter["part"]).strip()
        if part != current_part:
            lines.extend([f"### {part}", ""])
            current_part = part

        chapter_number += 1
        source_path = PROJECT_ROOT / str(chapter["source"])
        source_link = Path(
            os.path.relpath(
                source_path.resolve(strict=False),
                landing_path.parent.resolve(strict=False),
            )
        ).as_posix()

        lines.append(
            f"{chapter_number}. [{chapter['title']}]({source_link})"
        )

    lines.extend(
        [
            "",
            "## Cập nhật bài gộp",
            "",
            "Sau khi sửa một chapter:",
            "",
            "````powershell",
            "python -m scripts.build_unified_documentation",
            "python -m scripts.build_unified_documentation --check",
            "````",
            "",
            "File `PROJECT_DOCUMENTATION.md` là generated artifact; mọi thay "
            "đổi nội dung phải được thực hiện ở source chapter tương ứng.",
            "",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


def expected_outputs(
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[Path, str]:
    manifest = load_manifest(manifest_path)
    return {
        PROJECT_ROOT / str(manifest["output"]): build_book(manifest),
        PROJECT_ROOT / str(manifest["landing_page"]): build_landing_page(
            manifest
        ),
    }


def write_outputs(manifest_path: Path = DEFAULT_MANIFEST) -> None:
    for path, content in expected_outputs(manifest_path).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        print(f"Wrote: {path.relative_to(PROJECT_ROOT)}")


def check_outputs(manifest_path: Path = DEFAULT_MANIFEST) -> list[str]:
    errors: list[str] = []

    for path, expected in expected_outputs(manifest_path).items():
        if not path.exists():
            errors.append(
                f"Thiếu generated documentation: "
                f"{path.relative_to(PROJECT_ROOT)}"
            )
            continue

        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            errors.append(
                f"Generated documentation đã cũ: "
                f"{path.relative_to(PROJECT_ROOT)}"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Không ghi file; thất bại nếu generated docs đã cũ.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
    )
    arguments = parser.parse_args()

    try:
        if arguments.check:
            errors = check_outputs(arguments.manifest)
            if errors:
                for error in errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                print(
                    "Chạy: python -m scripts.build_unified_documentation",
                    file=sys.stderr,
                )
                return 1

            print("UNIFIED DOCUMENTATION CHECK SUCCESS")
            return 0

        write_outputs(arguments.manifest)
        print("UNIFIED DOCUMENTATION BUILD SUCCESS")
        return 0
    except DocumentationBuildError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
