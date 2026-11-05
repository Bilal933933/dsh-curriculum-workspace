#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مشغّل خط التحويل الكامل لكتاب واحد (عملية واحدة مستقلة — Unattended)
====================================================================
الغرض:
    تشغيل كل خط التحويل داخل عملية واحدة بلا تدخل بشري:
      1. استخراج الطبقة النصية (0 توكن) — وإن غابت، رسم الصفحات الناقصة فقط
         وتحويلها بصريًا عبر run_vision_batch.py.
      2. إعادة محاولة الصفحات الفاشلة (حتى محاولتين).
      3. مراجعة نصية رخيصة للمشبوه (review_text_batch.py --llm).
      4. مراجعة بصرية للكتب/الصفحات التي مرّت عبر OCR (اختيارية).
      5. تقرير نهائي في السجل.

كل المفاتيح والموديلات تُقرأ من `.env` عبر السكريبتات المستدعاة — لا مفاتيح هنا.

الملفات التي يقرؤها:
    curriculum_raw/<book>.pdf  (أو --pdf)
    .env

الملفات التي يكتبها:
    output/<book>/page_XXX.md
    curriculum_raw/<book>_images/page_XXX.png   (للصفحات التي تحتاج OCR فقط)
    logs/<book>_pipeline.log
    logs/chapters/<book>/{text_layer_report.md,ocr_needed.txt,text_review_log.md,review_log.md}

الاستخدام:
    python scripts/run_book_pipeline.py --book "اللغة_العربية_الصف_الخامس_ت1" --workers 2
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def log(msg: str, path: Path):
    line = time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def run(args, log_path: Path) -> int:
    """يشغّل سكريبتًا ويحوّل مخرجاته إلى ملف السجل."""
    with log_path.open("a", encoding="utf-8") as fh:
        p = subprocess.run([PY] + args, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT)
    return p.returncode


def missing_pages(book: str, total: int) -> list[int]:
    out = ROOT / "output" / book
    return [p for p in range(1, total + 1) if not (out / f"page_{p:03d}.md").exists()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True, help="اسم مجلد الكتاب (عربي)")
    ap.add_argument("--pdf", default=None, help="مسار PDF (افتراضي: curriculum_raw/<book>.pdf)")
    ap.add_argument("--pages", type=int, default=0, help="عدد الصفحات (0 = تلقائي)")
    ap.add_argument("--workers", type=int, default=2, help="توازي التحويل البصري")
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--retries", type=int, default=2, help="محاولات إضافية للصفحات الفاشلة")
    ap.add_argument("--skip-vision-review", action="store_true")
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    log_path = Path(args.log) if args.log else ROOT / "logs" / f"{args.book}_pipeline.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = Path(args.pdf) if args.pdf else ROOT / "curriculum_raw" / f"{args.book}.pdf"
    if not pdf.is_absolute():
        pdf = ROOT / pdf

    import pymupdf
    total = args.pages or pymupdf.open(pdf).page_count

    log(f"===== START book={args.book} pages={total} workers={args.workers} =====", log_path)
    log(f"PDF: {pdf}", log_path)

    # ---------- 1) الطبقة النصية (0 توكن) + OCR للصفحات الناقصة فقط ----------
    log("STEP1: text-layer extract (+ OCR only for missing pages)", log_path)
    code = run(["scripts/convert/pdf_text_extract.py", "--pdf", str(pdf), "--book", args.book,
                "--ocr-missing", "--workers", str(args.workers)], log_path)
    log(f"STEP1_EXIT: {code}", log_path)

    # ---------- 2) إعادة محاولة الصفحات الفاشلة ----------
    for attempt in range(1, args.retries + 1):
        gaps = missing_pages(args.book, total)
        if not gaps:
            break
        log(f"STEP2: retry {attempt} — missing {len(gaps)}: {gaps[:15]}", log_path)
        # ضمان وجود الصور لهذه الصفحات ثم تحويلها
        img_dir = ROOT / "curriculum_raw" / f"{args.book}_images"
        need_img = [p for p in gaps if not (img_dir / f"page_{p:03d}.png").exists()]
        if need_img:
            run(["scripts/convert/pdf_to_images.py", "--pdf", str(pdf),
                 "--out", str(img_dir)], log_path)
        run(["scripts/convert/run_vision_batch.py", "--book", args.book,
             "--start", "1", "--end", str(total),
             "--workers", str(args.workers), "--timeout", str(args.timeout)], log_path)

    # ---------- 3) مراجعة نصية رخيصة ----------
    log("STEP3: text review (flags + cheap llm fix)", log_path)
    run(["scripts/review/review_text_batch.py", "--book", args.book,
         "--start", "1", "--end", str(total), "--flags-only"], log_path)
    run(["scripts/review/review_text_batch.py", "--book", args.book,
         "--start", "1", "--end", str(total), "--llm"], log_path)

    # ---------- 4) مراجعة بصرية إن كان في الكتاب صفحات OCR ----------
    ocr_file = ROOT / "logs" / "chapters" / args.book / "ocr_needed.txt"
    if ocr_file.exists() and ocr_file.read_text(encoding="utf-8").strip() and not args.skip_vision_review:
        log("STEP4: vision review (book contains OCR pages)", log_path)
        run(["scripts/review/review_batch.py", "--book", args.book, "--start", "1",
             "--end", str(total), "--sample", "0.02", "--timeout", "120"], log_path)

    # ---------- 5) الحصيلة ----------
    gaps = missing_pages(args.book, total)
    made = total - len(gaps)
    log(f"===== DONE book={args.book} md={made}/{total} gaps={gaps[:20]} =====", log_path)
    return 0 if not gaps else 1


if __name__ == "__main__":
    sys.exit(main())
