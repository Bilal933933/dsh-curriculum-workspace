#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سكريبت استخراج صور صفحات PDF (PDF → PNG Rasterizer)
====================================================
الغرض:
    تحويل كتاب PDF مصوّر (بلا طبقة نصية) إلى صور PNG، صفحة واحدة لكل ملف،
    لتُغذّى بعد ذلك إلى سكربت التحويل البصري `run_vision_batch.py`.

المميزات:
    - لا يعيد توليد الصور الموجودة مسبقًا (آمن للتكرار والاستكمال).
    - يقبل مدى صفحات (--start/--end) لاستخراج عيّنة قبل التشغيل الكامل.
    - الدقة الافتراضية 260 dpi مطابقة لدقة كتاب «كيف تتقن النحو» (1700×2585).

الملفات التي يقرأها:
    - ملف PDF المحدد في --pdf.

الملفات التي يكتبها:
    - <out>/page_XXX.png  (صورة لكل صفحة).

الاستخدام:
    python scripts/pdf_to_images.py --pdf curriculum_raw/كيف_تتقن_البلاغة.pdf \
        --out curriculum_raw/كيف_تتقن_البلاغة_images --start 1 --end 5
"""

import argparse
import sys
from pathlib import Path

import pymupdf  # PyMuPDF

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="تحويل صفحات PDF إلى صور PNG")
    ap.add_argument("--pdf", required=True, help="مسار ملف PDF")
    ap.add_argument("--out", required=True, help="مجلد الصور الناتجة")
    ap.add_argument("--dpi", type=int, default=260, help="دقة الرسم (افتراضي 260)")
    ap.add_argument("--start", type=int, default=1, help="أول صفحة (1-based)")
    ap.add_argument("--end", type=int, default=0, help="آخر صفحة (0 = حتى النهاية)")
    ap.add_argument("--force", action="store_true", help="إعادة توليد الصور الموجودة")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    out = Path(args.out)
    if not pdf.exists():
        print(f"خطأ: لا يوجد ملف PDF: {pdf}")
        return 2

    out.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)

    total = doc.page_count
    end = min(args.end or total, total)
    if not (1 <= args.start <= end):
        print(f"خطأ: مدى غير صالح {args.start}–{end} (الكتاب {total} صفحة)")
        return 2

    zoom = args.dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)

    made = skipped = 0
    span = end - args.start + 1
    print(f"[*] الكتاب: {pdf.name} | الصفحات: {total} | المدى: {args.start}–{end} | {args.dpi} dpi")

    for i in range(args.start, end + 1):
        dest = out / f"page_{i:03d}.png"
        if dest.exists() and dest.stat().st_size > 10_000 and not args.force:
            skipped += 1
            continue
        page = doc[i - 1]
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pix.save(str(dest))
        made += 1
        print(f"[{made + skipped}/{span}] page_{i:03d}.png {pix.width}x{pix.height} "
              f"{dest.stat().st_size // 1024}KB", flush=True)

    print(f"[✓] تم: {made} صورة جديدة | {skipped} موجودة مسبقًا | إجمالي صفحات الكتاب {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
