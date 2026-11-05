"""خط سير مهمة «التقرير»: من Markdown إلى PDF.

وظيفة هذا الملف: ربط الخطوات ببعضها فقط (تنسيق)، دون تنفيذ أي خطوة بنفسه.

النسخ: `variant` يحدّد أسماء الملفات من `config.VARIANTS`
       (full = المفصّل · brief = الموجز).
"""

from __future__ import annotations

from pathlib import Path

import config
import markdown_html
import page_render
import pdf_print
from markdown_io import extract_title, read_text, strip_first_h1, write_text


def report_folder(slug: str) -> Path:
    """يعيد مجلد البحث ويتحقق من وجوده."""
    folder = config.DOCS_DIR / slug
    if not folder.is_dir():
        raise FileNotFoundError(f"لا يوجد مجلد بحث بهذا الاسم: {folder}")
    return folder


def variant_names(variant: str = config.DEFAULT_VARIANT) -> dict:
    """يعيد أسماء الملفات للنسخة المطلوبة."""
    if variant not in config.VARIANTS:
        raise ValueError(f"نسخة غير معروفة: {variant}")
    return config.VARIANTS[variant]


def build_html(slug: str, *, variant: str = config.DEFAULT_VARIANT,
               title: str | None = None, subtitle: str = "",
               author: str = "", kicker: str | None = None,
               day: str | None = None) -> Path:
    """يبني HTML للنسخة المطلوبة من مصدرها Markdown ويعيد مساره."""
    names = variant_names(variant)
    folder = report_folder(slug)
    source = folder / names["source"]
    if not source.is_file():
        raise FileNotFoundError(f"لا يوجد ملف {names['source']} في: {folder}")

    md_text = read_text(source)
    body_md, toc_html = markdown_html.to_html(strip_first_h1(md_text))

    html_document = page_render.compose(
        template=page_render.load_template(),
        styles=page_render.load_styles(),
        title=title or extract_title(md_text),
        subtitle=subtitle,
        kicker=kicker or config.DEFAULT_KICKER,
        meta=page_render.build_meta(author=author, day=day),
        toc=toc_html,
        body=body_md,
    )

    return write_text(folder / names["html"], html_document)


def print_pdf(slug: str, variant: str = config.DEFAULT_VARIANT) -> Path:
    """يطبع HTML النسخة المطلوبة إلى PDF ويعيد مساره."""
    names = variant_names(variant)
    folder = report_folder(slug)
    html_path = folder / names["html"]
    if not html_path.is_file():
        raise FileNotFoundError(
            f"لا يوجد {names['html']}. شغّل خطوة البناء أولًا."
        )
    return pdf_print.print_pdf(html_path, folder / names["pdf"])


def make(slug: str, *, variant: str = config.DEFAULT_VARIANT,
         **options) -> tuple[Path, Path]:
    """ينفّذ البناء والطبع معًا للنسخة المطلوبة."""
    html_path = build_html(slug, variant=variant, **options)
    pdf_path = print_pdf(slug, variant=variant)
    return html_path, pdf_path
