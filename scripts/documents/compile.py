"""تجميع أقسام متعددة في مستند واحد.

وظيفة هذا الملف: قراءة `البحوث/<slug>/sections/*.md` بترتيب أسمائها،
وحذف كتل `<!-- overflow … -->`، ودمجها في `report.md` بعنوان واحد.
لا يكتب أي قسم، ولا يبني ولا يطبع.

الاستخدام:
    python scripts/documents/compile.py --slug التنوين --title "التنوين: حدّه وأنواعه وأحكامه"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import config
from markdown_io import write_text

# كتلة مادة لا تخصّ القسم — تُحذف عند الدمج
_OVERFLOW_RE = re.compile(r"<!--\s*overflow.*?-->", re.S)


def sections_dir(slug: str) -> Path:
    """يعيد مجلد الأقسام ويتحقق من وجوده."""
    folder = config.DOCS_DIR / slug / "sections"
    if not folder.is_dir():
        raise FileNotFoundError(f"لا يوجد مجلد أقسام: {folder}")
    return folder


def read_sections(folder: Path) -> list[tuple[Path, str]]:
    """يقرأ الأقسام مرتّبة، ويحذف كتل overflow من كل قسم."""
    parts: list[tuple[Path, str]] = []
    for path in sorted(folder.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        clean = _OVERFLOW_RE.sub("", text).strip()
        if clean:
            parts.append((path, clean))
    if not parts:
        raise FileNotFoundError(f"لا توجد أقسام في: {folder}")
    return parts


def compile_document(slug: str, title: str, intro: str = "") -> Path:
    """يدمج الأقسام في report.md ويعيد مساره."""
    parts = read_sections(sections_dir(slug))
    blocks = [f"# {title}".strip()]
    if intro.strip():
        blocks.append(intro.strip())
    blocks.extend(text for _, text in parts)

    document = "\n\n".join(blocks) + "\n"
    return write_text(config.DOCS_DIR / slug / config.SOURCE_NAME, document)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="دمج أقسام markdown في مستند واحد")
    parser.add_argument("--slug", required=True, help="اسم مجلد البحث")
    parser.add_argument("--title", required=True, help="عنوان المستند في الغلاف")
    parser.add_argument("--intro", default="", help="فقرة تمهيدية اختيارية")
    args = parser.parse_args(argv)

    try:
        path = compile_document(args.slug, args.title, args.intro)
        parts = read_sections(sections_dir(args.slug))
    except (FileNotFoundError, OSError) as exc:
        print(f"[خطأ] {exc}", file=sys.stderr)
        return 1

    words = len(path.read_text(encoding="utf-8").split())
    print(f"[دمج] {len(parts)} قسمًا إلى {path}")
    print(f"[حجم] {words} كلمة تقريبًا")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
