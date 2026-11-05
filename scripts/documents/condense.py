"""توليد نسخة موجزة من الأقسام: الجوهر بلا فروع.

وظيفة هذا الملف: أخذ كل قسم من `sections/` وإبقاء:
    ١) عنوان القسم
    ٢) فقرته التأسيسية الأولى
    ٣) أول جدول فيه
    ٤) أول صندوق (فرق/تنبيه/ملاحظة)
    ٥) سطر المصادر
وحذف كل `###` وما تحته. لا يكتب نصًّا جديدًا ولا يضيف معلومة.

الاستخدام:
    python scripts/documents/condense.py --slug التنوين --title "التنوين في صفحتين"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import config
from markdown_io import write_text

_HEADING_RE = re.compile(r"^##\s")
_SUBHEADING_RE = re.compile(r"^###\s")
_CALLOUT_RE = re.compile(r"^>\s*\*\*(فرق|تنبيه|ملاحظة):\*\*")
_SOURCES_RE = re.compile(r"^\*\*المصادر:\*\*")
_TABLE_RE = re.compile(r"^\|")


def split_blocks(text: str) -> list[str]:
    """يفصل النص إلى كتل تفصلها أسطر فارغة."""
    return [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]


def condense_section(text: str) -> str:
    """يعيد نسخة موجزة من قسم واحد."""
    blocks = split_blocks(text)
    heading = ""
    intro = ""
    table = ""
    callout = ""
    sources = ""

    for block in blocks:
        first = block.splitlines()[0]
        if not heading and _HEADING_RE.match(first):
            heading = block
            continue
        if _SUBHEADING_RE.match(first):
            continue
        if _SOURCES_RE.match(block) and not sources:
            sources = block
            continue
        if _CALLOUT_RE.match(block) and not callout:
            callout = block
            continue
        if _TABLE_RE.match(first) and not table:
            table = block
            continue
        if not intro and not _CALLOUT_RE.match(block) and not _TABLE_RE.match(first):
            intro = block

    parts = [p for p in (heading, intro, table, callout, sources) if p]
    return "\n\n".join(parts)


def condense_document(slug: str, title: str) -> Path:
    """يبني `report_brief.md` من الأقسام ويعيد مساره."""
    folder = config.DOCS_DIR / slug / "sections"
    if not folder.is_dir():
        raise FileNotFoundError(f"لا يوجد مجلد أقسام: {folder}")

    briefs: list[str] = []
    for path in sorted(folder.glob("*.md")):
        brief = condense_section(path.read_text(encoding="utf-8"))
        if brief:
            briefs.append(brief)
    if not briefs:
        raise FileNotFoundError(f"لم يُستخرج شيء من: {folder}")

    document = "\n\n".join([f"# {title}", *briefs]) + "\n"
    return write_text(config.DOCS_DIR / slug / config.BRIEF_SOURCE_NAME, document)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="توليد نسخة موجزة من الأقسام")
    parser.add_argument("--slug", required=True, help="اسم مجلد البحث")
    parser.add_argument("--title", required=True, help="عنوان النسخة الموجزة")
    args = parser.parse_args(argv)

    try:
        path = condense_document(args.slug, args.title)
    except (FileNotFoundError, OSError) as exc:
        print(f"[خطأ] {exc}", file=sys.stderr)
        return 1

    words = len(path.read_text(encoding="utf-8").split())
    print(f"[موجز] {path}")
    print(f"[حجم] {words} كلمة تقريبًا")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
