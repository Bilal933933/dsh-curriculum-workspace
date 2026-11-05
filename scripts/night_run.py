# -*- coding: utf-8 -*-
"""night_run.py — مراقب ليلي لمهمة تفريغ كتابَي الأضواء (ص4 + ص6) ثم تسجيلهما.

لماذا
-----
التفريغ يستغرق ساعات، والمستخدم ينام. هذا السكريبت يعمل مستقلًا في الخلفية:
    1. ينتظر انتهاء عمليات `pipeline_external_book.py` الجارية.
    2. يعيد تشغيل التفريغ لأي كتاب ناقص (استئناف: يتجاهل الصفحات المنجزة)،
       بحد أقصى 3 محاولات لكل كتاب. رمز الخروج 3 = نفاد الحصة ⇒ ينتظر ثم يعيد
       بلا احتساب محاولة (حتى الساعة 10:00 صباحًا كحد أقصى).
    3. يسجّل كل كتاب مكتمل عبر `scripts/retrieval/onboard_book.py`
       (يضيف مدخلًا في meta/catalog.yaml + يبني index + يولّد toc.draft.yaml).
    4. يكتب ملخصًا في `logs/external/night_summary.md` وسطرًا في
       `scripts/execution_log.md`.
    5. يغلق الجهاز (shutdown /s /t 60) — إلا إذا مُرِّر `--no-shutdown`.

يقرأ: output/<book>/*.md، meta/catalog.yaml، curriculum_raw/<book>.pdf
يكتب: output/<book>/… (عبر الـ pipeline)، index/<book>/، meta/catalog.yaml،
       meta/books/<id>/toc.draft.yaml، logs/external/، scripts/execution_log.md

الاستخدام:
    python -X utf8 scripts/night_run.py              # تنفيذ كامل ثم إغلاق الجهاز
    python -X utf8 scripts/night_run.py --no-shutdown --once   # للاختبار
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
LOG_DIR = ROOT / "logs" / "external"
NIGHT_LOG = LOG_DIR / "night_run.log"
SUMMARY = LOG_DIR / "night_summary.md"

MAX_RESUME_ATTEMPTS = 3      # لكل كتاب، لأخطاء الصفحات لا لنفاد الحصة
QUOTA_SLEEP = 20 * 60        # انتظار بعد نفاد الحصة (ثانية)
POLL = 90                    # دورة الفحص (ثانية)
DEADLINE_HOURS = 10          # أقصى مدة عمل قبل التوقف (ساعات)

TITLES = {
    "السادس": "الأضواء — اللغة العربية — الصف السادس الابتدائي — الفصل الدراسي الأول",
    "الرابع": "الأضواء — اللغة العربية — الصف الرابع الابتدائي — الفصل الدراسي الأول",
}

BOOKS = [
    {
        "book": "الأضواء_اللغة_العربية_الصف_السادس_الابتدائي_ت1",
        "total": 466,
        "id": "adwaa_ar_p6_t1",
        "title": TITLES["السادس"],
    },
    {
        "book": "الأضواء_اللغة_العربية_الصف_الرابع_الابتدائي_ت1",
        "total": 446,
        "id": "adwaa_ar_p4_t1",
        "title": TITLES["الرابع"],
    },
]

META = {
    "author": "نخبة من خبراء المناهج والتعليم",
    "publisher": "نهضة مصر — سلسلة الأضواء",
    "subject": "اللغة العربية: قراءة ونصوص ونحو وإملاء وتعبير",
    "notes": "كتاب خارجي (مساعد تعليمي) لا مقرر وزاري؛ يُذكر بوصفه مصدرًا مساعدًا ولا يُستشهد به بدل المقرر.",
}


def log(msg: str) -> None:
    """سطر موحّد بالطابع الزمني في السجل الليلي والكونسول."""
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with NIGHT_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def done_pages(book: str) -> int:
    """عدد الصفحات المنجزة فعلًا (ملف > 100 بايت — نفس معيار الـ pipeline)."""
    d = ROOT / "output" / book
    if not d.is_dir():
        return 0
    return sum(1 for p in d.glob("page_*.md") if p.stat().st_size > 100)


def running_pipelines() -> bool:
    """هل ما زالت هناك عملية تفريغ حيّة؟ (فحص CommandLine عبر CIM)."""
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Select-Object -ExpandProperty CommandLine"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        ).stdout
    except Exception as exc:  # noqa: BLE001
        log(f"[!] تعذّر فحص العمليات: {exc}")
        return False
    return "pipeline_external_book.py" in (out or "")


def run_pipeline(book: str) -> int:
    """تشغيل/استئناف تفريغ كتاب واحد، وإرجاع رمز الخروج."""
    pdf = ROOT / "curriculum_raw" / f"{book}.pdf"
    out_path = LOG_DIR / f"night_{book}.out"
    log(f"[>] استئناف تفريغ: {book}")
    cmd = [
        PY, "-u", "-X", "utf8", str(ROOT / "scripts" / "convert" / "pipeline_external_book.py"),
        "--pdf", str(pdf), "--chunk", "40", "--workers", "3", "--timeout", "120", "--dpi", "200",
    ]
    with out_path.open("a", encoding="utf-8", errors="replace") as fh:
        proc = subprocess.run(cmd, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT)
    log(f"[<] انتهى {book} برمز {proc.returncode} | منجز {done_pages(book)}")
    return proc.returncode


def register(book_meta: dict) -> str:
    """تسجيل كتاب مكتمل في catalog + بناء الفهرس + مسوّدة الفهرسة."""
    cmd = [
        PY, "-X", "utf8", str(ROOT / "scripts" / "retrieval" / "onboard_book.py"),
        "--book", book_meta["book"], "--id", book_meta["id"], "--title", book_meta["title"],
        "--author", META["author"], "--publisher", META["publisher"],
        "--subject", META["subject"], "--notes", META["notes"],
    ]
    log(f"[+] تسجيل: {book_meta['id']}")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    tail = (proc.stdout or "").strip().splitlines()[-3:]
    for line in tail:
        log(f"    {line}")
    if proc.returncode == 0:
        return "مسجَّل جديدًا"
    if proc.returncode == 2:
        return "مسجَّل مسبقًا"
    return f"فشل التسجيل (رمز {proc.returncode})"


def past_deadline(started: datetime) -> bool:
    """هل تجاوزنا أقصى مدة عمل (DEADLINE_HOURS من بدء المراقب)؟"""
    return (datetime.now() - started).total_seconds() >= DEADLINE_HOURS * 3600


def keep_awake() -> None:
    """يمنع دخول الجهاز في السكون ما دام المراقب يعمل (بلا تغيير دائم في الطاقة)."""
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        log("[i] مُنع السكون التلقائي أثناء تشغيل المراقب")
    except Exception as exc:  # noqa: BLE001
        log(f"[!] تعذّر منع السكون: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="مراقب ليلي: تفريغ ثم تسجيل ثم إغلاق")
    ap.add_argument("--no-shutdown", action="store_true", help="لا تغلق الجهاز في النهاية")
    ap.add_argument("--once", action="store_true", help="فحص واحد بلا انتظار (لاختبار)")
    args = ap.parse_args()

    log("=== بدء المراقب الليلي ===")
    keep_awake()
    started = datetime.now()
    attempts = {b["book"]: 0 for b in BOOKS}

    while not args.once:
        counts = {b["book"]: done_pages(b["book"]) for b in BOOKS}
        log("[*] " + " | ".join(f"{b['id']}: {counts[b['book']]}/{b['total']}" for b in BOOKS))
        if all(counts[b["book"]] >= b["total"] for b in BOOKS):
            log("[✓] اكتمل الكتابان")
            break
        if past_deadline(started):
            log(f"[!] تجاوزنا {DEADLINE_HOURS} ساعات — إيقاف")
            break
        if running_pipelines():
            time.sleep(POLL)
            continue

        # لا عملية حيّة وهناك نقص ⇒ استئناف
        progressed = False
        for b in BOOKS:
            if done_pages(b["book"]) >= b["total"]:
                continue
            if attempts[b["book"]] >= MAX_RESUME_ATTEMPTS:
                continue
            attempts[b["book"]] += 1
            rc = run_pipeline(b["book"])
            if rc == 3:                     # نفاد الحصة: انتظار طويل بلا احتساب محاولة
                attempts[b["book"]] -= 1
                log(f"[⏳] نفاد الحصة — انتظار {QUOTA_SLEEP // 60} دقيقة")
                time.sleep(QUOTA_SLEEP)
            progressed = True
        if not progressed:
            log("[!] لا تقدّم ممكن (استنفدت المحاولات) — توقف")
            break

    # ---- التسجيل ----
    results = []
    for b in BOOKS:
        got = done_pages(b["book"])
        if got >= b["total"]:
            status = register(b)
        else:
            status = f"غير مكتمل ({got}/{b['total']}) — لم يُسجَّل"
        results.append((b["book"], b["id"], got, b["total"], status))
        log(f"[i] {b['id']}: {status}")

    # ---- الملخص ----
    lines = [
        "# ملخص المراقب الليلي",
        "",
        f"الوقت: {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "| الكتاب | المعرّف | الصفحات | النتيجة |",
        "|---|---|---|---|",
    ]
    for book, bid, got, total, status in results:
        lines.append(f"| {book} | `{bid}` | {got}/{total} | {status} |")
    log_lines = []
    if NIGHT_LOG.exists():
        log_lines = NIGHT_LOG.read_text(encoding="utf-8").splitlines()[-40:]
    lines += ["", "## آخر 40 سطرًا من السجل", "", "```"] + log_lines + ["```", ""]
    SUMMARY.write_text("\n".join(lines), encoding="utf-8")
    log(f"[i] الملخص: {SUMMARY}")

    # ---- سطر في سجل التنفيذ ----
    entry = (
        f"\n- **{time.strftime('%Y-%m-%d %H:%M')}** — تفريغ ليلي: "
        + " · ".join(f"{bid} {got}/{total} ({status})" for _, bid, got, total, status in results)
        + ".\n"
    )
    with (ROOT / "scripts" / "execution_log.md").open("a", encoding="utf-8") as f:
        f.write(entry)

    if args.no_shutdown or args.once:
        log("=== انتهى بلا إغلاق (--no-shutdown/--once) ===")
        return 0

    log("[⏻] إغلاق الجهاز بعد 60 ثانية")
    subprocess.run(["shutdown", "/s", "/t", "60", "/c", "اكتمل التفريغ والتسجيل — إغلاق ليلي"], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
