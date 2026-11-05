"""تركيب صفحة HTML كاملة: قالب + أنماط + غلاف + فهرس + محتوى.

وظيفة هذا الملف: تجميع الأجزاء في مستند واحد، بلا تحويل Markdown ولا طبع.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import config
from markdown_io import read_text


def load_template(name: str = "report.html") -> str:
    """يقرأ قالب HTML من مجلد الأصول."""
    path = config.ASSETS_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"لا يوجد قالب بهذا الاسم: {path}")
    return read_text(path)


def load_styles() -> str:
    """يدمج ملفات الأنماط بالترتيب المحدد في الإعدادات."""
    parts: list[str] = []
    for name in config.STYLE_FILES:
        path = config.ASSETS_DIR / name
        if path.is_file():
            parts.append(f"/* ==== {name} ==== */\n" + read_text(path))
    if not parts:
        raise FileNotFoundError(f"لا توجد ملفات أنماط في: {config.ASSETS_DIR}")
    return "\n\n".join(parts)


def build_meta(author: str = "", day: str | None = None) -> str:
    """يبني أسطر بيانات الغلاف."""
    lines: list[str] = []
    if author:
        lines.append(f"إعداد: {author}")
    lines.append(f"التاريخ: {day or date.today().isoformat()}")
    return "<br>".join(lines)


def compose(*, template: str, styles: str, title: str, subtitle: str,
            kicker: str, meta: str, toc: str, body: str) -> str:
    """يستبدل علامات القالب بالقيم الفعلية."""
    values = {
        "{{STYLES}}": styles,
        "{{TITLE}}": title,
        "{{SUBTITLE}}": subtitle,
        "{{KICKER}}": kicker,
        "{{META}}": meta,
        "{{TOC}}": toc,
        "{{BODY}}": body,
        "{{LANG}}": config.DEFAULT_LANG,
        "{{DIR}}": config.DEFAULT_DIR,
        "{{PAGE_SIZE}}": config.PAGE_SIZE,
    }
    output = template
    for key, value in values.items():
        output = output.replace(key, value)
    return output


def resolve_output(folder: Path, name: str) -> Path:
    """يعيد مسار ملف داخل مجلد البحث."""
    return folder / name
