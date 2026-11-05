"""تحويل نص Markdown إلى HTML مع فهرس آلي.

وظيفة هذا الملف: التحويل وحده — لا قراءة ملفات، ولا قوالب، ولا طبع.
"""

from __future__ import annotations

import re

import markdown

# extra يشمل: الجداول، الرموز البرمجية المسوّرة، القوائم التعريفية، الحواشي
EXTENSIONS = ("extra", "sane_lists", "toc")

EXTENSION_CONFIG = {
    "toc": {
        "toc_depth": "1-2",   # الفهرس يعرض العنوان الرئيسي وأقسامه
        "anchorlink": False,
    }
}

# صناديق العقد: «> **فرق:** …» ← عنصر مميّز بلون
CALLOUT_LABELS = {
    "فرق": "farq",
    "تنبيه": "tanbih",
    "ملاحظة": "mulahaza",
}

_BLOCKQUOTE_RE = re.compile(r"<blockquote>(.*?)</blockquote>", re.S)
_CALLOUT_START_RE = re.compile(
    r"^\s*<p><strong>(?P<label>" + "|".join(CALLOUT_LABELS) + r"):</strong>"
)
_SOURCES_RE = re.compile(r"<p><strong>المصادر:</strong>(.*?)</p>", re.S)


def _promote_callouts(html: str) -> str:
    """يحوّل الاقتباسات الموسومة (فرق/تنبيه/ملاحظة) إلى صناديق ملوّنة."""

    def replace(match: re.Match[str]) -> str:
        inner = match.group(1)
        start = _CALLOUT_START_RE.match(inner)
        if not start:
            return match.group(0)
        label = start.group("label")
        body = inner[start.end():]
        body = re.sub(r"</p>\s*$", "", body.strip())
        return (
            f'<div class="callout callout--{CALLOUT_LABELS[label]}">'
            f'<span class="callout__label">{label}</span>{body}</div>'
        )

    return _BLOCKQUOTE_RE.sub(replace, html)


def _mark_sources(html: str) -> str:
    """يمنح فقرة «المصادر» صنفًا خاصًّا ليظهر في تذييل القسم."""
    return _SOURCES_RE.sub(r'<p class="sources"><strong>المصادر:</strong>\1</p>', html)


def to_html(md_text: str) -> tuple[str, str]:
    """يعيد (نص المحتوى HTML، فهرس المحتويات HTML)."""
    md = markdown.Markdown(
        extensions=list(EXTENSIONS),
        extension_configs=EXTENSION_CONFIG,
    )
    body = md.convert(md_text)
    body = _promote_callouts(body)
    body = _mark_sources(body)
    return body, md.toc
