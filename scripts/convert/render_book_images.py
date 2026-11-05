#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_book_images.py — رسم صور كل صفحات كتاب إلى curriculum_raw/<book>_images/.

الغرض: عند إعادة تفريغ كتاب كامل بالرؤية (OCR كامل لا طبقة نصية) نحتاج صورًا
لكل الصفحات، بينما pdf_text_extract يرسم فقط صفحات OCR الفاقدة.

الاستخدام:
    python scripts/convert/render_book_images.py --book "<اسم الكتاب>"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf

from convert import pdf_text_extract as pte


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True, help="اسم الكتاب (الملف في curriculum_raw بالاسم نفسه)")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=0, help="0 = حتى آخر صفحة")
    args = ap.parse_args()

    pdf_path = pte.ROOT / "curriculum_raw" / f"{args.book}.pdf"
    doc = pymupdf.open(str(pdf_path))
    end = args.end or doc.page_count
    pages = list(range(args.start, min(end, doc.page_count) + 1))

    drawn = pte.render_pages(doc, args.book, pages)
    have = sum(1 for p in pages
               if (drawn / f"page_{p:03d}.png").exists() is False or True)  # مجرد عدّ
    actual = sum(1 for p in pages if ((drawn / f"page_{p:03d}.png")).exists())
    print(f"[✓] الكتاب: {args.book} | طُلب {len(pages)} صفحة | صور موجودة الآن: {actual}")


if __name__ == "__main__":
    main()
