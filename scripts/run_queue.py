#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_queue.py — مدير طابور التحويل اللامركزي (Unattended Queue Manager)
=====================================================================
الغرض:
    تشغيل تحويل عدة كتب "بالتوازي" في عملية واحدة مستقلة، بلا تدخل بشري،
    حتى تنتهي كلها — ثم تسجيل الكتب المكتملة في طبقة الاسترجاع آليًّا.

    كل كتاب يُنفَّذ في عملية بايثون منفصلة (run_book_pipeline.py)، والمفاتيح
    والموديلات يأتيان من `.env` عبر السكريبتات المستدعاة — لا مفاتيح هنا.

ما يفعله لكل كتاب:
    1. نسخ ملف PDF إلى curriculum_raw/ (إن كان ناقصًا أو مختلف الحجم).
    2. تشغيل خط التحويل الكامل (نصّي ← OCR للناقص ← إعادة محاولات ← مراجعة).
    3. قياس الفجوات؛ فإن بقيت صفحات: انتظار متزايد وإعادة المحاولة
       (يعالج نفاد حصة المفاتيح مؤقتًا، ويعالج انقطاع الشبكة).
    4. بعد اكتمال كل الكتب: تسجيل كل كتاب في meta/catalog.yaml وبناء فهرسه
       وتوليد مسوّدة toc.draft.yaml (عبر onboard_book.py).

الإصلاحات الصغيرة:
    REPAIRS: صفحات معدودة فشلت سابقًا في كتاب منتهٍ — يُعاد تحويلها وحدها.

الملفات التي يقرؤها:
    ملفات PDF في Downloads (المسارات في BOOKS)
    .env (عبر السكريبتات المستدعاة)
    meta/catalog.yaml (لفحص التسجيل المسبق)

الملفات التي يكتبها:
    curriculum_raw/<book>.pdf            (نسخة المصدر)
    curriculum_raw/<book>_images/*.png   (صور الصفحات)
    output/<book>/page_XXX.md            (المخرجات)
    logs/<book>_pipeline.log             (سجل كل كتاب)
    logs/<book>_console.log(.err)        (مخرجات الكونسول)
    logs/queue.log + logs/queue_summary.md
    meta/catalog.yaml + index/<book>/ + meta/books/<id>/toc.draft.yaml  (عند التسجيل)

الاستخدام:
    python scripts/run_queue.py --dry-run          # فحص بلا تشغيل
    python scripts/run_queue.py                    # التشغيل الكامل (خلفية)
    python scripts/run_queue.py --only arabic_p1_t1
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf

# ضمان طباعة العربية على كونسول ويندوز
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
RAW = ROOT / "curriculum_raw"
OUT = ROOT / "output"
LOGS = ROOT / "logs"
CATALOG = ROOT / "meta" / "catalog.yaml"
ENV_PATH = ROOT / ".env"

LOCK = threading.Lock()
MINISTRY = "وزارة التربية والتعليم والتعليم الفني — جمهورية مصر العربية"
PUBLISHER = "وزارة التربية والتعليم والتعليم الفني — مصر"
SUBJECT = "اللغة العربية: قراءة ونصوص وقواعد نحوية وإملائية وخط عربي"

# ------------------------------------------------------------------ الكتب المطلوبة
# src: المسار الأصلي | book: اسم مجلد المخرجات | id: معرّف لاتيني
BOOKS = [
    dict(book="اللغة_العربية_الصف_الأول_ت1", id="arabic_p1_t1",
         src=r"C:\Users\blals\Downloads\Arabic_language_prim1_t1.pdf",
         title="اللغة العربية — الصف الأول الابتدائي — الفصل الدراسي الأول",
         author=MINISTRY, subject=SUBJECT, publisher=PUBLISHER),
    dict(book="اللغة_العربية_الصف_الثاني_ت1", id="arabic_p2_t1",
         src=r"C:\Users\blals\Downloads\Arabic_language_prim2_t1.pdf",
         title="اللغة العربية — الصف الثاني الابتدائي — الفصل الدراسي الأول",
         author=MINISTRY, subject=SUBJECT, publisher=PUBLISHER),
    dict(book="اللغة_العربية_الصف_الأول_الإعدادي_ت1", id="arabic_prep1_t1",
         src=r"C:\Users\blals\Downloads\Arabic_Prep1_T1.pdf",
         title="اللغة العربية — الصف الأول الإعدادي — الفصل الدراسي الأول",
         author=MINISTRY, subject=SUBJECT, publisher=PUBLISHER),
    dict(book="اللغة_العربية_الصف_الثاني_الإعدادي_ت1", id="arabic_prep2_t1",
         src=r"C:\Users\blals\Downloads\Arabic_language_prep2_t1.pdf",
         title="اللغة العربية — الصف الثاني الإعدادي — الفصل الدراسي الأول",
         author=MINISTRY, subject=SUBJECT, publisher=PUBLISHER),
    dict(book="اللغة_العربية_الصف_الثالث_الإعدادي_ت1", id="arabic_prep3_t1",
         src=r"C:\Users\blals\Downloads\Arabic_language_prep3_t1.pdf",
         title="اللغة العربية — الصف الثالث الإعدادي — الفصل الدراسي الأول",
         author=MINISTRY, subject=SUBJECT, publisher=PUBLISHER),
    dict(book="الإعراب_الميسر", id="erab_muyassar",
         src=r"C:\Users\blals\Downloads\lis_gr2316.pdf",
         title="الإعراب الميسر في اللغة العربية",
         author="د. محمد إبراهيم عبادة",
         subject="النحو: الإعراب — مكوناته وأنواعه وعلاماته",
         publisher="غير موثّق في الملفات المتاحة"),
]

# كتب تعمل الآن أو اكتملت في جلسة سابقة — تُسجَّل في الفهرس فقط عند نهايتها
# (لا تُشغَّل هنا كي لا تتعارض عمليتان على المجلد نفسه).
META_ONLY = {
    "اللغة_العربية_الصف_الثالث_ت1": dict(id="arabic_p3_t1",
        title="اللغة العربية — الصف الثالث الابتدائي — الفصل الدراسي الأول"),
    "اللغة_العربية_الصف_الرابع_ت1": dict(id="arabic_p4_t1",
        title="اللغة العربية — الصف الرابع الابتدائي — الفصل الدراسي الأول"),
    "اللغة_العربية_الصف_الخامس_ت1": dict(id="arabic_p5_t1",
        title="اللغة العربية — الصف الخامس الابتدائي — الفصل الدراسي الأول"),
    "اللغة_العربية_الصف_السادس_ت1": dict(id="arabic_p6_t1",
        title="اللغة العربية — الصف السادس الابتدائي — الفصل الدراسي الأول"),
}

# صفحات فشلت في كتاب منتهٍ (فجوات موثّقة) — إعادة محاولة وحدها.
# سببها السابق: رفض النص القصير المشروع في فواصل الوحدات (أُصلح في run_vision_batch).
REPAIRS = [
    ("اللغة_العربية_الصف_الثالث_ت1", [6, 67, 83]),
    ("اللغة_العربية_الصف_الرابع_ت1", [7, 55]),
    ("اللغة_العربية_الصف_الخامس_ت1", [7, 53, 99, 146]),
]

MAX_ATTEMPTS = 6          # محاولات خط التحويل لكل كتاب
FIRST_WAIT_MIN = 10       # انتظار أول بين المحاولات (يتزايد)
MAX_WAIT_MIN = 40
IDLE_MINUTES = 10         # كتاب "متوقف" إذا لم يُكتب سجله منذ هذه المدة
SWEEP_DEADLINE_MIN = 180  # أقصى انتظار للكتب الخارجية قبل التسجيل


# ------------------------------------------------------------------ أدوات
def log(msg: str, tag: str = "") -> None:
    line = time.strftime("[%Y-%m-%d %H:%M:%S] ") + (f"[{tag}] " if tag else "") + msg
    with LOCK:
        print(line, flush=True)
        LOGS.mkdir(parents=True, exist_ok=True)
        with (LOGS / "queue.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def env_keys() -> int:
    """عدد المفاتيح في .env (بلا طباعة قيمها)."""
    if not ENV_PATH.exists():
        return 0
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if raw.strip().startswith("GEMINI_OCR_KEYS"):
            value = raw.split("=", 1)[1]
            return len([k for k in value.split(",") if k.strip()])
    return 0


def page_total(pdf: Path) -> int:
    with pymupdf.open(pdf) as doc:
        return doc.page_count


def gaps(book: str, total: int) -> list[int]:
    d = OUT / book
    return [p for p in range(1, total + 1) if not (d / f"page_{p:03d}.md").exists()]


def run(args: list[str], stdout_path: Path | None = None) -> int:
    """يشغّل أمرًا بايثون ويعيد رمز الخروج (المخرجات إلى ملف إن حُدّد)."""
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    if stdout_path is None:
        return subprocess.run([PY] + args, cwd=str(ROOT), env=env).returncode
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("a", encoding="utf-8") as fh:
        p = subprocess.run([PY] + args, cwd=str(ROOT), env=env,
                           stdout=fh, stderr=subprocess.STDOUT)
    return p.returncode


def copy_pdf(b: dict) -> Path:
    src = Path(b["src"])
    dest = RAW / f"{b['book']}.pdf"
    if not src.exists():
        raise FileNotFoundError(f"لا يوجد ملف المصدر: {src}")
    if dest.exists() and dest.stat().st_size == src.stat().st_size:
        log(f"PDF موجود مسبقًا: {dest.name} ({dest.stat().st_size // 1_000_000} MB)", b["id"])
        return dest
    RAW.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    log(f"نُسخ PDF ← {dest.name} ({dest.stat().st_size // 1_000_000} MB)", b["id"])
    return dest


# ------------------------------------------------------------------ تحويل كتاب
def convert(b: dict, index: int, workers: int, stagger_s: int) -> dict:
    tag = b["id"]
    book = b["book"]
    time.sleep(index * stagger_s)          # إطلاق متدرّج لتخفيف ضغط الرسم على القرص
    result = dict(book=book, id=b["id"], ok=False, total=0, made=0, gaps=[], attempts=0)

    try:
        pdf = copy_pdf(b)
        total = page_total(pdf)
    except Exception as exc:
        log(f"تعذّر تجهيز المصدر: {exc}", tag)
        return result

    result["total"] = total
    console = LOGS / f"{book}_console.log"
    (OUT / book).mkdir(parents=True, exist_ok=True)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        result["attempts"] = attempt
        left = gaps(book, total)
        if not left:
            log(f"مكتمل مسبقًا: {total}/{total}", tag)
            break
        log(f"محاولة {attempt}/{MAX_ATTEMPTS} — متبقٍ {len(left)} صفحة", tag)
        code = run(["scripts/run_book_pipeline.py", "--book", book,
                    "--pages", str(total), "--workers", str(workers),
                    "--timeout", "120", "--retries", "2"], stdout_path=console)
        left = gaps(book, total)
        log(f"انتهت المحاولة {attempt} (exit={code}) — متبقٍ {len(left)}: {left[:12]}", tag)
        if not left:
            break
        if attempt < MAX_ATTEMPTS:
            wait = min(FIRST_WAIT_MIN * attempt, MAX_WAIT_MIN)
            log(f"انتظار {wait} دقيقة (حصة/شبكة) ثم إعادة المحاولة", tag)
            time.sleep(wait * 60)

    left = gaps(book, total)
    result.update(ok=not left, made=total - len(left), gaps=left)
    log(f"حصيلة: {total - len(left)}/{total}" + (f" — فجوات {left[:15]}" if left else " ✓"), tag)
    return result


# ------------------------------------------------------------------ إصلاحات صغيرة
def repair_pages() -> None:
    for book, pages in REPAIRS:
        if not (OUT / book).is_dir():
            continue
        for p in pages:
            dst = OUT / book / f"page_{p:03d}.md"
            if dst.exists() and dst.stat().st_size > 100:
                continue
            img = RAW / f"{book}_images" / f"page_{p:03d}.png"
            if not img.exists():
                continue
            for attempt in (1, 2):
                log(f"إصلاح صفحة {p} (محاولة {attempt})", book)
                run(["scripts/convert/run_vision_batch.py", "--book", book,
                     "--start", str(p), "--end", str(p),
                     "--workers", "1", "--timeout", "120"],
                    stdout_path=LOGS / f"{book}_repair.log")
                if dst.exists() and dst.stat().st_size > 100:
                    log(f"نجحت الصفحة {p}", book)
                    break


# ------------------------------------------------------------------ التسجيل
def catalog_text() -> str:
    return CATALOG.read_text(encoding="utf-8") if CATALOG.exists() else ""


def registered(book_id: str) -> bool:
    return f"- id: {book_id}" in catalog_text()


def idle_minutes(book: str) -> float:
    """دقائق منذ آخر كتابة في سجلات الكتاب (لكشف أنه توقّف)."""
    marks = []
    for p in (LOGS / f"{book}_pipeline.log", LOGS / f"{book}_console.log"):
        if p.exists():
            marks.append(time.time() - p.stat().st_mtime)
    return min(marks) / 60 if marks else 1e9


def onboard(book: str, meta: dict, dry: bool = False) -> bool:
    bid = meta["id"]
    if registered(bid):
        log(f"مسجَّل مسبقًا في catalog.yaml — تخطي", bid)
        return False
    total_hint = ""
    pdf = RAW / f"{book}.pdf"
    if pdf.exists():
        total_hint = f" ({page_total(pdf)} صفحة في المصدر)"
    log(f"تسجيل الكتاب في طبقة الاسترجاع{total_hint}", bid)
    code = run(["scripts/retrieval/onboard_book.py", "--book", book, "--id", bid,
                "--title", meta["title"],
                "--author", meta.get("author", MINISTRY),
                "--subject", meta.get("subject", SUBJECT),
                "--publisher", meta.get("publisher", PUBLISHER)],
               stdout_path=LOGS / "onboarding.log")
    log(f"نتيجة التسجيل exit={code}", bid)
    return code == 0


def sweep_onboard(deadline_min: int = SWEEP_DEADLINE_MIN) -> list[str]:
    """يسجّل كل مجلد مخرجات غير مسجَّل، بعد التأكد أن عملياته توقّفت."""
    started = time.time()
    done: list[str] = []
    pending = []
    for d in sorted(OUT.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        meta = next((b for b in BOOKS if b["book"] == d.name), None) or META_ONLY.get(d.name)
        if not meta:
            continue
        if registered(meta["id"]):
            continue
        pending.append((d.name, meta))

    if not pending:
        log("لا كتب بحاجة إلى تسجيل — كلها مسجَّلة")
        return done

    # انتظار الكتب التي ما زالت تكتب (٣ و٤ و٥) حتى تتوقف أو ينقضي الأجل.
    while (time.time() - started) / 60 < deadline_min:
        busy = [b for b, _ in pending if idle_minutes(b) < IDLE_MINUTES]
        if not busy:
            break
        log(f"انتظار كتب ما زالت تعمل: {busy} — فحص بعد 5 دقائق")
        time.sleep(300)

    for book, meta in pending:
        if idle_minutes(book) < IDLE_MINUTES:
            log(f"تخطّي التسجيل: ما زال يعمل ({book})", meta["id"])
            continue
        try:
            if onboard(book, meta):
                done.append(book)
        except Exception as exc:
            log(f"فشل التسجيل: {exc}", meta["id"])
    return done


# ------------------------------------------------------------------ التشغيل
def main() -> int:
    ap = argparse.ArgumentParser(description="مدير طابور التحويل اللامركزي")
    ap.add_argument("--workers", type=int, default=1,
                    help="توازي التحويل البصري داخل كل كتاب (الافتراضي 1)")
    ap.add_argument("--stagger", type=int, default=25,
                    help="ثوانٍ بين إطلاق كل كتاب وآخر (الافتراضي 25)")
    ap.add_argument("--only", default=None, help="معرّف كتاب واحد للتشغيل")
    ap.add_argument("--skip-repairs", action="store_true")
    ap.add_argument("--skip-onboard", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="فحص بلا تنفيذ ولا كتابة")
    args = ap.parse_args()

    books = [b for b in BOOKS if not args.only or b["id"] == args.only]
    if not books:
        print(f"لا كتاب بالمعرّف: {args.only}")
        return 2

    keys = env_keys()
    log(f"===== بدء الطابور | كتب {len(books)} | مفاتيح {keys} =====")
    if keys == 0:
        log("خطأ: لا مفاتيح في .env — توقف")
        return 2

    # ---------- فحص أولي ----------
    plan = []
    for b in books:
        src = Path(b["src"])
        if not src.exists():
            log(f"مصدر مفقود: {src}", b["id"])
            continue
        total = page_total(src)
        plan.append((b, total, len(gaps(b["book"], total))))
        log(f"خطة: {b['book']} | {total} صفحة | متبقٍ {plan[-1][2]} | مسجَّل: {registered(b['id'])}", b["id"])

    if args.dry_run:
        log(f"[فحص] سأشغّل {len(plan)} كتابًا بالتوازي (workers={args.workers} لكل كتاب). لا كتابة.")
        return 0

    # ---------- إصلاحات (في خيط منفصل كي لا تؤخّر إطلاق الكتب) ----------
    if not args.skip_repairs and not args.only:
        threading.Thread(target=repair_pages, daemon=True).start()

    # ---------- التحويل بالتوازي ----------
    results = []
    with ThreadPoolExecutor(max_workers=max(1, len(plan))) as ex:
        futs = [ex.submit(convert, b, i, args.workers, args.stagger)
                for i, (b, _, _) in enumerate(plan)]
        for f in futs:
            try:
                results.append(f.result())
            except Exception as exc:
                log(f"خيط فشل: {exc}")

    # ---------- التسجيل ----------
    onboarded: list[str] = []
    if not args.skip_onboard:
        onboarded = sweep_onboard()

    # ---------- الملخص ----------
    lines = ["# ملخص عملية التحويل بالتوازي", "",
             f"- **التاريخ:** {time.strftime('%Y-%m-%d %H:%M')}",
             f"- **المفاتيح:** {keys} | **توازي لكل كتاب:** {args.workers}",
             f"- **الكتب المشغَّلة:** {len(results)}", "",
             "| الكتاب | المعرّف | المحوَّل | المحاولات | الحالة |",
             "|---|---|---|---|---|"]
    for r in sorted(results, key=lambda x: x["id"]):
        state = "مكتمل ✓" if r["ok"] else f"ناقص {len(r['gaps'])}: {r['gaps'][:8]}"
        lines.append(f"| {r['book']} | {r['id']} | {r['made']}/{r['total']} | {r['attempts']} | {state} |")
    if onboarded:
        lines += ["", "## كُتب سُجّلت في طبقة الاسترجاع"] + [f"- {b}" for b in onboarded]
    summary = LOGS / "queue_summary.md"
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok = sum(1 for r in results if r["ok"])
    log(f"===== انتهى الطابور: مكتمل {ok}/{len(results)} | سُجّل {len(onboarded)} | {summary.relative_to(ROOT)} =====")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
