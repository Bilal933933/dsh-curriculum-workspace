"""قراءة وكتابة نصوص Markdown، واستخراج بيانات الترويسة منها.

وظيفة هذا الملف: التعامل مع الملفات النصية فقط، بلا تحويل ولا عرض.
"""

from __future__ import annotations

from pathlib import Path


def read_text(path: Path) -> str:
    """يقرأ ملف نصي بترميز UTF-8."""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> Path:
    """يكتب ملفًا نصيًّا بترميز UTF-8، وينشئ مجلده إن لزم."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def extract_title(md_text: str, fallback: str = "تقرير") -> str:
    """يستخرج أول عنوان من المستوى الأول (#) لاستخدامه عنوانًا للمستند."""
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def strip_first_h1(md_text: str) -> str:
    """يحذف أول عنوان (#) لأن العنوان يُعرض في الغلاف."""
    lines = md_text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            return "\n".join(lines[:index] + lines[index + 1:])
    return md_text
