# -*- coding: utf-8 -*-
"""
pipeline_external_book.py — تفريغ كتاب كامل (مصدر خارجي) على دفعات.

لماذا
-----
الكتب الكاملة في مجلد الأضواء ممسوحة (بلا طبقة نص) وبعدد صفحات كبير
(مثال: 468 صفحة). رسم كل الصفحات دفعةً واحدة يستهلك مساحة ويجعل الاستئناف
مستحيلًا. هذا السكربت يعمل بدفعات: يرسم 40 صفحة ← يفرّغها ← التالية.

ما يقرأه
--------
`curriculum_raw/<name>.pdf` (يجب نسخه أولًا).

ما يكتبه
--------
`curriculum_raw/<name>_images/page_XXX.png` (صور الدفعة)
`output/<name>/page_XXX.md`                  (النص المحوَّل)
`logs/external/<name>.log`                   (سجل التقدّم)

الاستخدام
---------
    python scripts/convert/pipeline_external_book.py --pdf "curriculum_raw/X.pdf" --dry-run
    python scripts/convert/pipeline_external_book.py --pdf "curriculum_raw/X.pdf"
    python scripts/convert/pipeline_external_book.py --pdf "..." --start 1 --end 120
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdf_text_extract import render_pages  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

LOG_DIR = ROOT / "logs" / "external"


def log(line: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    print(f"[{stamp}] {line}", flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def done_pages(book: str) -> set[int]:
    d = ROOT / "output" / book
    if not d.is_dir():
        return set()
    return {int(p.stem[5:8]) for p in d.glob("page_*.md") if p.stat().st_size > 100}


def main() -> int:
    ap = argparse.ArgumentParser(description="تفريغ كتاب كامل على دفعات")
    ap.add_argument("--pdf", required=True, help="مسار PDF داخل curriculum_raw")
    ap.add_argument("--book", default=None, help="اسم مجلد المخرجات (افتراضي: اسم PDF)")
    ap.add_argument("--chunk", type=int, default=40, help="عدد صفحات الدفعة")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=0, help="0 = آخر صفحة")
    ap.add_argument("--dpi", type=int, default=200, help="دقة الرسم (200 توازن جودة/حجم)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    if not pdf.is_absolute():
        pdf = ROOT / pdf
    if not pdf.is_file():
        log(f"[!] لا يوجد ملف: {pdf}")
        return 2

    book = args.book or pdf.stem
    doc = pymupdf.open(str(pdf))
    total = doc.page_count
    end = args.end or total
    end = min(end, total)
    have = done_pages(book)
    todo = [p for p in range(args.start, end + 1) if p not in have]

    log(f"[*] الكتاب: {book} | صفحات: {total} | مطلوب: {args.start}–{end} | منجز: {len(have)} | متبقٍ: {len(todo)}")
    if not todo:
        log("[✓] لا شيء متبقٍ")
        return 0
    if args.dry_run:
        for i in range(0, len(todo), args.chunk):
            batch = todo[i:i + args.chunk]
            log(f"    دفعة: {batch[0]}–{batch[-1]} ({len(batch)} ص)")
        return 0

    started = time.time()
    for i in range(0, len(todo), args.chunk):
        batch = todo[i:i + args.chunk]
        a, b = batch[0], batch[-1]
        log(f"[>] دفعة {a}–{b} ({len(batch)} ص): رسم الصور…")
        render_pages(doc, book, batch, dpi=args.dpi)
        cmd = [
            sys.executable, str(ROOT / "scripts" / "convert" / "run_vision_batch.py"),
            "--book", book, "--start", str(a), "--end", str(b),
            "--workers", str(args.workers), "--timeout", str(args.timeout),
        ]
        p = subprocess.run(cmd, cwd=str(ROOT), text=True, encoding="utf-8", errors="replace")
        now = done_pages(book)
        log(f"[<] بعد الدفعة: منجز {len(now)}/{end} | رمز الخروج {p.returncode}")
        if p.returncode == 3:
            log("[⛔] نفاد المفاتيح/الحصص — إيقاف آمن. أعد التشغيل لاحقًا (يستأنف).")
            return 3

    elapsed = time.time() - started
    final = done_pages(book)
    log(f"[✓] انتهى: {len(final)}/{end} صفحة في {elapsed/60:.1f} دقيقة")
    return 0 if len(final) >= end else 1


if __name__ == "__main__":
    sys.exit(main())
