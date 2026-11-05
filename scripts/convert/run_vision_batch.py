#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سكريبت التحويل البصري (Vision OCR Pipeline) — إصدار متوازٍ
===========================================================
الغرض:
    تحويل صور صفحات الكتاب إلى Markdown منظم (تشكيل كامل + جداول)،
    مع حلقة تدوير ذكية (موديلات × مفاتيح) ومعالجة متوازية متعددة الصفحات.

التحسينات عن النسخة السابقة:
    - --workers N : معالجة N صفحات في نفس الوقت (الافتراضي 3).
    - --timeout S : مهلة الطلب الواحد (الافتراضي 90 ثانية بدل 240)
      حتى لا تعلق دفعة كاملة 4 دقائق على طلب معلّق واحد.
    - حلقة التدوير آمنة مع الخيوط (Thread-safe).
    - خروج برمز 3 عند نفاد كل المفاتيح/الموديلات (لإيقاف الحلقة الخارجية).

الاستخدام:
    python scripts/convert/run_vision_batch.py --book "كيف_تتقن_النحو" \
        --start 161 --end 170 --workers 3 --timeout 90

    --book إلزامي: لا كتاب افتراضي، حتى لا يُحوَّل كتاب بالخطأ بصمت
    (كان BOOK = "كيف_تتقن_النحو" سابقًا، فأي تشغيل بلا --book يكتب هناك).
"""

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# إتاحة استيراد الوحدة المشتركة scripts/lib/ عند التشغيل المباشر.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from lib.gemini_client import QuotaRing, encode_image, generate, load_env

# ضمان طباعة العربية والرموز بشكل صحيح على كونسول ويندوز
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ------------------------------------------------------------------ المسارات
ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT / ".env"

# لا تُضبط هذه المسارات إلا من --book داخل main()؛ لا كتاب افتراضي.
BOOK = ""
IMAGE_DIR = Path()
OUTPUT_DIR = Path()
LOG_DIR = Path()
LOG_PATH = Path()
ERRORS_PATH = Path()


def set_book(book: str) -> None:
    """يوجّه كل مسارات التشغيل إلى الكتاب المطلوب (نقطة الضبط الوحيدة)."""
    global BOOK, IMAGE_DIR, OUTPUT_DIR, LOG_DIR, LOG_PATH, ERRORS_PATH
    BOOK = book
    IMAGE_DIR = ROOT / "curriculum_raw" / f"{book}_images"
    OUTPUT_DIR = ROOT / "output" / book
    LOG_DIR = ROOT / "logs" / "chapters" / book
    LOG_PATH = LOG_DIR / "conversion_log.md"
    ERRORS_PATH = LOG_DIR / "errors.md"

PROMPT = """حوّل صورة صفحة الكتاب هذه إلى Markdown نظيف ودقيق.

القواعد:
1. استخرج كل النص العربي حرفيًا كما هو، مع الحفاظ على التشكيل الكامل (الحركات) كما يظهر في الصورة.
2. حافظ على علامات الترقيم العربية والرموز (﴿ ﴾ ، ؛ : -).
3. الجداول تُحوّل إلى جداول Markdown، والآيات والأحاديث تُوضع كما هي دون تعديل.
4. استخدم العناوين (#، ##، ###) حسب التسلسل الهرمي الظاهر في الصفحة.
5. لا تضف أي شرح أو تعليق أو مقدمة من عندك، ولا تكتب "إليك النص".
6. إذا كانت الصفحة فارغة أو صورة فقط، اكتب فقط: [صفحة فارغة]
7. في صفحات الفهرس: اكتب كل مدخل مرة واحدة فقط، ولا تكتب نقاطًا قائدة (.....) إطلاقًا، ولا تكرر أي سطر.
8. سطور الفراغات المنقّطة في الأنشطة (..... أو ……) تُكتب مرة واحدة فقط بهذا الشكل: …… — لا تمدّها ولا تكررها في سطور متتالية.
9. أخرج Markdown فقط.
"""

# ------------------------------------------------------------------ الإعدادات
def load_settings() -> dict:
    env = load_env(ENV_PATH)
    keys = [k.strip() for k in env.get("GEMINI_OCR_KEYS", "").split(",") if k.strip()]
    if not keys:
        sys.exit("خطأ: لا توجد مفاتيح في GEMINI_OCR_KEYS داخل .env")

    if env.get("GEMINI_OCR_MODELS", "").strip():
        models = [m.strip() for m in env["GEMINI_OCR_MODELS"].split(",") if m.strip()]
    else:
        models = [env.get("GEMINI_OCR_MODEL", "gemini-3.1-flash-lite")]
        if env.get("GEMINI_OCR_FALLBACK", "").strip():
            models.append(env["GEMINI_OCR_FALLBACK"].strip())

    return {
        "keys": keys,
        "models": models,
        "batch": int(env.get("BATCH_SIZE", "10") or 10),
    }


# ------------------------------------------------------------------ صلاحية النص


def _usable(text: str) -> bool:
    """نصّ مقبول؟ صفحات الفواصل والعناوين نصّها قصير مشروع (سطر أو سطران).

    المعيار: وجود 6 حروف عربية على الأقل، لا طول النص. (الطول وحده كان يرفض
    فواصل الوحدات وأغلفة الأبواب فيحوّلها إلى فجوات دائمة.)
    """
    arabic = sum(1 for ch in (text or "") if "\u0621" <= ch <= "\u064a")
    if arabic >= 6:
        return True
    latin = sum(1 for ch in (text or "")
                if ("a" <= ch <= "z") or ("A" <= ch <= "Z"))
    return latin >= 20


def is_blank_image(path: Path) -> bool:
    """يكشف الصفحة البيضاء تمامًا (بلا نص) — يوفّر نداء النموذج كاملًا."""
    try:
        with Image.open(path) as im:
            g = im.convert("L")
            g.thumbnail((400, 400))
            ex = g.getextrema()
        return ex[1] - ex[0] < 12
    except Exception:
        return False


# ------------------------------------------------------------------ إصلاح التكرار
DOTS_CHARS = ".·…_-ـ•—"
MAX_REASONABLE_TEXT = 40_000   # أطول نص مقبول لصفحة واحدة


def _is_dots_line(line: str) -> bool:
    """سطر فراغ منقّط (نقاط/شرطات/تطويل فقط)؟ — لا يحمل معلومة.

    صفحات الأنشطة مليئة بها، والنموذج يمدّها حتى نفاد `maxOutputTokens`،
    فيخرج نص > 40k حرف. تُطبَّع إلى `……` قبل فحص التكرار حتى تُضغط.
    """
    s = line.strip()
    if len(s) < 8:
        return False
    dots = sum(1 for ch in s if ch in DOTS_CHARS)
    return dots / len(s) >= 0.6


def repair_repetition(text: str, max_dup: int = 3) -> tuple[str, int, bool]:
    """يكشف انفلات النموذج (تكرار السطر نفسه مئات المرات) ويضغطه.

    بعض صفحات الفهارس ذات النقاط الطويلة وسطور الفراغات المنقّطة تدفع النموذج
    إلى تكرار سطر واحد حتى نفاد maxOutputTokens، فيخرج ملف بحجم 100KB لسطر واحد.

    الترتيب مهم: نطبّع سطور النقاط أولًا (أطوالها مختلفة فلا يلتقطها فحص
    «السطر المتطابق»)، ثم نضغط التكرار، ثم نحكم بالانفلات على **النص النظيف**
    فقط. الحكم قبل التنظيف كان يرمي صفحات سليمة (11 صفحة تفشل في كل تشغيل).

    يعيد (النص، المحذوف، انفلات؟).
    """
    lines = text.splitlines()
    out, prev, run = [], None, 0
    removed_dots = removed_content = 0
    for ln in lines:
        is_dots = _is_dots_line(ln)
        if is_dots:
            ln = "……"
        if ln.strip() and ln == prev:
            run += 1
            if run > max_dup:
                if is_dots:
                    removed_dots += 1
                else:
                    removed_content += 1
                continue
        else:
            run = 0
        out.append(ln)
        prev = ln

    cleaned = "\n".join(out)
    if len(cleaned) > MAX_REASONABLE_TEXT:
        return "", removed_dots + removed_content, True   # انفلات حقيقي
    if removed_content >= 100:                            # تكرار محتوى انفلاتي
        return "", removed_dots + removed_content, True
    return cleaned, removed_dots + removed_content, False


# ------------------------------------------------------------------ معالجة صفحة واحدة (خيط)
def _process_page(page, ring, force, timeout):
    img_path = IMAGE_DIR / f"page_{page:03d}.png"
    out_path = OUTPUT_DIR / f"page_{page:03d}.md"

    if not img_path.exists():
        return page, "skip_img", ""
    if out_path.exists() and out_path.stat().st_size > 100 and not force:
        return page, "skip_done", ""

    # صفحة بيضاء فعلًا: تُكتب بعلامة موحّدة بلا أي نداء (توفير توكنز)
    if force is False and is_blank_image(img_path) and not out_path.exists():
        out_path.write_text("[صفحة فارغة]\n", encoding="utf-8")
        return page, "ok", {"model": "blank", "len": 13, "in": 0, "out": 0, "dropped": 0}

    try:
        image_b64 = encode_image(img_path)
    except Exception as exc:
        return page, "fail", f"صورة: {exc}"

    parts = [
        {"text": PROMPT},
        {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
    ]
    text, model, usage, err = generate(ring, parts, timeout=timeout)
    if err:
        if "نفدت كل" in str(err):
            return page, "quota", str(err)
        return page, "fail", str(err)

    # نقبل أي نص فيه 6 حروف عربية على الأقل (صفحات العناوين/الفواصل)
    if _usable(text):
        text, dropped, runaway = repair_repetition(text)
        if runaway:
            out_path.unlink(missing_ok=True)
            return page, "fail", f"تكرار انفلاتي — أُعيدت للمحاولة ({dropped} سطر)"
        if not _usable(text):
            out_path.unlink(missing_ok=True)
            return page, "fail", f"نص غير صالح بعد ضغط التكرار ({dropped} سطر)"
        try:
            out_path.write_text(text.rstrip() + "\n", encoding="utf-8")
        except Exception as exc:
            return page, "fail", f"كتابة: {exc}"
        return page, "ok", {
            "model": model,
            "len": len(text),
            "in": usage.get("promptTokenCount", 0),
            "out": usage.get("candidatesTokenCount", 0),
            "dropped": dropped,
        }
    return page, "fail", "نص قصير/فارغ"


# ------------------------------------------------------------------ التشغيل
def main():
    parser = argparse.ArgumentParser(description="تحويل صفحات الكتاب إلى Markdown")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--force", action="store_true", help="إعادة التحويل حتى لو الملف موجود")
    parser.add_argument("--workers", type=int, default=3, help="عدد الصفحات المتوازية")
    parser.add_argument("--timeout", type=int, default=90, help="مهلة الطلب الواحد بالثواني")
    parser.add_argument("--book", required=True, help="اسم الكتاب (مجلد الصور والمخرجات) — إلزامي")
    parser.add_argument("--model", default=None,
                        help="تجاوز موديلات .env (مفصولة بفواصل) — لصفحات عسيرة")
    args = parser.parse_args()

    # نقطة الضبط الوحيدة لكل المسارات (لا مسار افتراضي).
    set_book(args.book)

    settings = load_settings()
    if args.model:
        settings["models"] = [m.strip() for m in args.model.split(",") if m.strip()]
    ring = QuotaRing(settings["keys"], settings["models"])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_PATH.exists():
        LOG_PATH.write_text(f"# سجل تحويل الكتاب: {args.book}\n\n", encoding="utf-8")
    if not ERRORS_PATH.exists():
        ERRORS_PATH.write_text(f"# ذاكرة أخطاء التحويل — {args.book}\n\n", encoding="utf-8")

    print(f"[*] الموديلات: {' ← '.join(settings['models'])}")
    print(f"[*] المفاتيح: {len(settings['keys'])} | المدى: {args.start}–{args.end} | توازٍ: {args.workers} | مهلة: {args.timeout}s")

    pages = list(range(args.start, args.end + 1))
    results = {}
    quota_dead = False
    started = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_process_page, p, ring, args.force, args.timeout): p for p in pages}
        for fut in as_completed(futs):
            p = futs[fut]
            try:
                page, status, payload = fut.result()
            except Exception as exc:
                page, status, payload = p, "fail", f"خيط: {exc}"
            results[page] = (status, payload)
            if status == "quota":
                quota_dead = True

    ok = skipped = failed = 0

    with LOG_PATH.open("a", encoding="utf-8") as log, \
         ERRORS_PATH.open("a", encoding="utf-8") as errs:
        log.write(f"\n## دفعة {args.start}–{args.end} — {time.strftime('%Y-%m-%d %H:%M')} (توازٍ {args.workers})\n")

        for page in sorted(results):
            status, payload = results[page]
            if status == "skip_img":
                print(f"[!] {page}: الصورة غير موجودة — تخطي")
                log.write(f"- الصفحة {page}: الصورة غير موجودة (تخطي).\n")
                skipped += 1
            elif status == "skip_done":
                print(f"[=] {page}: منجزة مسبقًا — تخطي")
                log.write(f"- الصفحة {page}: منجزة مسبقًا (تخطي).\n")
                skipped += 1
            elif status == "ok":
                m = payload
                extra = f" | حُذف تكرار {m['dropped']} سطر" if m.get("dropped") else ""
                print(f"[✓] {page}: {m['len']} حرف | {m['model']} | in {m['in']}/out {m['out']}{extra}")
                log.write(f"- الصفحة {page}: تم ({m['model']}، {m['len']} حرف){extra}.\n")
                ok += 1
            elif status == "quota":
                print(f"[⛔] {page}: {payload} — إيقاف الدفعة")
                log.write(f"- الصفحة {page}: {payload} (إيقاف).\n")
                errs.write(f"- {time.strftime('%Y-%m-%d %H:%M')} | صفحة {page} | {payload}\n")
                failed += 1
            else:
                print(f"[✗] {page}: فشل — {payload}")
                log.write(f"- الصفحة {page}: فشل ({payload}).\n")
                errs.write(f"- {time.strftime('%Y-%m-%d %H:%M')} | صفحة {page} | {payload}\n")
                failed += 1

        elapsed = time.time() - started
        summary = f"**الملخص:** ناجح {ok} | متخطّى {skipped} | فاشل {failed} | {elapsed:.0f} ثانية | زوج فعّال {ring.alive_pairs()}/{len(ring.pairs)}.\n"
        log.write(summary)

    print(f"\n[*] انتهت الدفعة: ناجح {ok} | متخطّى {skipped} | فاشل {failed} | {elapsed:.0f}s")
    if quota_dead:
        return 3
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
