#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سكريبت مراجعة جودة مخرجات التحويل (Review Pipeline)
===================================================
الغرض:
    فحص مخرجات Markdown الصادرة من سكريبت التحويل، والتأكد من مطابقتها
    لصور الصفحات الأصلية (تشكيل + جداول + نصوص قرآنية)، مع تصحيح الأخطاء.

الاستراتيجية (انتقائية لتوفير التكلفة):
    1. فحص آلي رخيص (بدون نموذج) يعلّم الصفحات المشبوهة.
    2. مراجعة نموذج (أقوى) للصفحات المشبوهة + عينة عشوائية 5% من السليم.
    3. --all لمراجعة كل الصفحات (أبطأ وأغلى).

الملفات التي يقرأها:
    - .env                        (GEMINI_OCR_KEYS, GEMINI_REVIEW_MODEL)
    - output/<book>/page_XXX.md   (المخرجات المراد مراجعتها)
    - curriculum_raw/.../*.png    (الصور الأصلية)

الملفات التي يكتبها:
    - output/<book>/page_XXX.md   (النسخة المصححة فوق نفس الملف)
    - logs/chapters/<book>/review_log.md   (تقرير المراجعة)
    - logs/chapters/<book>/errors.md       (ذاكرة الأخطاء)

الاستخدام:
    python scripts/review_batch.py --start 1 --end 60
    python scripts/review_batch.py --start 1 --end 60 --all
"""

import argparse
import difflib
import math
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.gemini_client import encode_image, generate, load_env, QuotaRing  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ------------------------------------------------------------------ المسارات
ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT / ".env"
BOOK = ""  # يُضبط من --book الإلزامي فقط (لا كتاب افتراضي صامت)
IMAGE_DIR = ROOT / "curriculum_raw" / f"{BOOK}_images"
OUTPUT_DIR = ROOT / "output" / BOOK
LOG_DIR = ROOT / "logs" / "chapters" / BOOK
REVIEW_LOG = LOG_DIR / "review_log.md"
ERRORS_PATH = LOG_DIR / "errors.md"

REVIEW_PROMPT = """أنت مدقّق جودة للتحويل البصري من صورة كتاب عربي إلى Markdown.

سأعطيك:
1) صورة الصفحة الأصلية.
2) النص المستخرج حاليًا (Markdown).

قارن النص بالصورة حرفيًا:
- تأكد من اكتمال كل الكلمات والتشكيل (الحركات) كما في الصورة تمامًا.
- صحّح أي خطأ إملائي أو تشكيل أو ترتيب جدول.
- إذا كان النص مطابقًا تمامًا، أعد كتابته كما هو دون تغيير.
- لا تضف أي شرح أو تعليق أو مقدمة — أخرج Markdown المصحح فقط.
"""

ARABIC_LETTERS = re.compile("[\u0621-\u064A]")
ARABIC_DIACRITICS = re.compile("[\u064B-\u0652\u0670]")


# ------------------------------------------------------------------ الإعدادات
def load_review_settings():
    env = load_env(ENV_PATH)
    keys = [k.strip() for k in env.get("GEMINI_OCR_KEYS", "").split(",") if k.strip()]
    if not keys:
        sys.exit("خطأ: لا توجد مفاتيح في GEMINI_OCR_KEYS")
    model = env.get("GEMINI_REVIEW_MODEL", "gemini-3.5-flash").strip()
    fallback = env.get("GEMINI_REVIEW_FALLBACK", "").strip()
    models = [model] + ([fallback] if fallback and fallback != model else [])
    return keys, models


# ------------------------------------------------------------------ الفحص الآلي
def flags(text: str):
    """يعيد قائمة علامات الشبهة على النص المستخرج (بدون نموذج)."""
    fs = []
    t = text.strip()
    if len(t) < 150:
        fs.append("نص قصير")
    if "صفحة فارغة" in t or "محتوى مستخرج" in t or "محتوى تم" in t:
        fs.append("placeholder")
    letters = len(ARABIC_LETTERS.findall(t))
    diacritics = len(ARABIC_DIACRITICS.findall(t))
    if letters > 60 and diacritics < letters * 0.03:
        fs.append("تشكيل ناقص")
    if "|" in t and "---" not in t:
        pipe_lines = [ln for ln in t.splitlines() if "|" in ln]
        if len(pipe_lines) >= 2:
            fs.append("جدول مفكوك")
    return fs


def strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


# ------------------------------------------------------------------ النداء
def call_review(ring: QuotaRing, image_b64: str, current_text: str, timeout: int = 90):
    """يراجع صفحة واحدة عبر الحلقة. يعيد (corrected_text, err)."""
    parts = [
        {"text": REVIEW_PROMPT},
        {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
        {"text": f"النص المستخرج الحالي:\n\n{current_text}"},
    ]
    text, _model, _usage, err = generate(ring, parts, timeout=timeout, temperature=0.0)
    if err:
        return None, err
    return strip_fences(text), None


# ------------------------------------------------------------------ التشغيل
def main():
    global IMAGE_DIR, OUTPUT_DIR, LOG_DIR, REVIEW_LOG, ERRORS_PATH, BOOK
    parser = argparse.ArgumentParser(description="مراجعة جودة مخرجات التحويل")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--all", action="store_true", help="مراجعة كل الصفحات (بدون انتقاء)")
    parser.add_argument("--sample", type=float, default=0.05, help="نسبة العينة العشوائية من السليم")
    parser.add_argument("--book", required=True, help="اسم الكتاب (مجلد الصور والمخرجات) — إلزامي")
    parser.add_argument("--timeout", type=int, default=120, help="مهلة الطلب الواحد بالثواني")
    args = parser.parse_args()

    # توجيه المسارات إلى الكتاب المطلوب (لا افتراضي)
    BOOK = args.book
    IMAGE_DIR = ROOT / "curriculum_raw" / f"{args.book}_images"
    OUTPUT_DIR = ROOT / "output" / args.book
    LOG_DIR = ROOT / "logs" / "chapters" / args.book
    REVIEW_LOG = LOG_DIR / "review_log.md"
    ERRORS_PATH = LOG_DIR / "errors.md"

    keys, models = load_review_settings()
    ring = QuotaRing(keys, models)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not REVIEW_LOG.exists():
        REVIEW_LOG.write_text(f"# تقرير مراجعة الجودة — {BOOK}\n\n", encoding="utf-8")
    if not ERRORS_PATH.exists():
        ERRORS_PATH.write_text(f"# ذاكرة أخطاء التحويل — {BOOK}\n\n", encoding="utf-8")

    random.seed(42)

    # 1) فحص آلي
    suspect, clean = [], []
    for page in range(args.start, args.end + 1):
        out = OUTPUT_DIR / f"page_{page:03d}.md"
        if not out.exists():
            continue
        text = out.read_text(encoding="utf-8")
        fs = flags(text)
        if fs:
            suspect.append((page, text, fs))
        else:
            clean.append((page, text, []))

    # 2) انتقاء المراجعة
    sample_n = math.ceil(len(clean) * args.sample)
    sampled = random.sample(clean, min(sample_n, len(clean)))
    to_review = suspect + sampled
    if args.all:
        to_review = suspect + clean

    print(f"[*] موديل المراجعة: {' ← '.join(models)}")
    print(f"[*] الصفحات: {args.start}–{args.end} | مشبوه: {len(suspect)} | سليم: {len(clean)}")
    print(f"[*] ستراجع: {len(to_review)} صفحة (انتقائي)" if not args.all else f"[*] ستراجع الكل: {len(to_review)}")

    reviewed = changed = failed = 0
    changes = []

    with REVIEW_LOG.open("a", encoding="utf-8", buffering=1) as rlog, \
         ERRORS_PATH.open("a", encoding="utf-8", buffering=1) as errs:
        rlog.write(f"\n## مراجعة {args.start}–{args.end} — {time.strftime('%Y-%m-%d %H:%M')}\n")
        total_rev = len(to_review)

        for idx, (page, text, fs) in enumerate(sorted(to_review), 1):
            img = IMAGE_DIR / f"page_{page:03d}.png"
            out = OUTPUT_DIR / f"page_{page:03d}.md"
            if not img.exists():
                print(f"[!] {page}: صورة غير موجودة — تخطي", flush=True)
                continue

            print(f"[…] [{idx}/{total_rev}] صفحة {page}", flush=True)
            image_b64 = encode_image(img)
            corrected, err = call_review(ring, image_b64, text, args.timeout)

            if err:
                print(f"[✗] {page}: مراجعة فشلت — {err}", flush=True)
                errs.write(f"- {time.strftime('%Y-%m-%d %H:%M')} | مراجعة صفحة {page} | {err}\n")
                failed += 1
                continue
            if not corrected or len(corrected.strip()) <= 50:
                print(f"[=] {page}: مراجعة بلا نتيجة — أُبقي الأصل", flush=True)
                rlog.write(f"- صفحة {page}: مراجعة بلا نتيجة — أُبقي الأصل.\n")
                continue

            ratio = difflib.SequenceMatcher(None, text, corrected).ratio()
            reviewed += 1
            if ratio < 0.995:
                changed += 1
                changes.append((page, ratio, fs))

            out.write_text(corrected.rstrip() + "\n", encoding="utf-8")
            rlog.write(f"- صفحة {page}: روجعت (تشابه {ratio:.3f}) {'| علامات: '+', '.join(fs) if fs else ''}\n")
            print(f"[✓] {page}: تشابه {ratio:.3f} | {', '.join(fs) if fs else 'سليم'}", flush=True)
            time.sleep(random.uniform(0.3, 0.6))

        rlog.write(f"\n**الملخص:** روجعت {reviewed} | تغيّرت {changed} | فشلت {failed}.\n")

    print(f"\n[*] انتهت المراجعة: روجعت {reviewed} | تغيّرت {changed} | فشلت {failed}")
    if changes:
        print("[*] أعلى الصفحات تغييرًا:")
        for page, ratio, fs in sorted(changes, key=lambda x: x[1])[:5]:
            print(f"    - صفحة {page}: تشابه {ratio:.3f} | {', '.join(fs)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
