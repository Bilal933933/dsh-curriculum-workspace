"""مُشغّل التفريغ الشامل: 3 كتب متزامنة، وتسجيل كل كتاب فور اكتماله.

لكل كتاب: نسخ PDF ← رسم الصور ← تفريغ الرؤية ← إعادة الصفحات الفاشلة
← فحص الجودة ← تسجيل (onboard_book) ← بناء الخريطة (toc_review) ← تحقق.

التشغيل (من مجلد workspace، داخل .venv):
    python scripts/convert/pipeline_all.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "curriculum_raw"
OUT = ROOT / "output"
LOG = ROOT / "logs" / "pipeline_all.log"
SRC = Path(r"D:\المكتبة-التعليمية\01-كتب-مدرسية\1-ابتدائي")
LIB = Path(r"D:\المكتبة-التعليمية\01-كتب-مدرسية")
STAGE_DIRS = ("0-", "1-", "2-", "3-")
STAGE_WORDS = ("الابتدائي", "الإعدادي", "الثانوي")

MAX_PARALLEL_BOOKS = 3
VISION_WORKERS = 2
MAX_RETRY_ROUNDS = 4
AUTHOR = "وزارة التربية والتعليم والتعليم الفني — جمهورية مصر العربية"
PUBLISHER = "وزارة التربية والتعليم والتعليم الفني — مصر"

# (معرّف الكتاب، مجلد المصدر النسبي، مجلد المخرجات، عدد الصفحات، المادة في العنوان)
QUEUE: list[tuple[str, str, str, int, str]] = [
    # ---------------- الصف الخامس ----------------
    ("library_skills_p5_t1", r"الصف-الخامس\الترم-الأول\المكتبات-ومهارات-البحث\كتاب-الطالب\5ب-مكتبات-وزارة-كتاب-2027.pdf",
     "المكتبات_ومهارات_البحث_الصف_الخامس_الابتدائي_ت1", 21, "المكتبات ومهارات البحث"),
    ("agriculture_skills_p5_t1", r"الصف-الخامس\الترم-الأول\مهارات-الزراعة-وريادة-الأعمال\كتاب-الطالب\5ب-مهارات-زراعة-وزارة-كتاب-2027.pdf",
     "مهارات_الزراعة_الصف_الخامس_الابتدائي_ت1", 35, "مهارات الزراعة وريادة الأعمال"),
    ("ict_p5_t1", r"الصف-الخامس\الترم-الأول\تكنولوجيا-المعلومات-والاتصالات\كتاب-الطالب\5ب-تكنولوجيا-وزارة-كتاب-2027.pdf",
     "تكنولوجيا_المعلومات_والاتصالات_الصف_الخامس_الابتدائي_ت1", 46, "تكنولوجيا المعلومات والاتصالات"),
    # ---------------- الصف الرابع (المتبقي) ----------------
    ("agriculture_skills_p4_t1", r"الصف-الرابع\الترم-الأول\مهارات-الزراعة-وريادة-الأعمال\كتاب-الطالب\4ب-مهارات-زراعة-وزارة-كتاب-2027.pdf",
     "مهارات_الزراعة_الصف_الرابع_الابتدائي_ت1", 33, "مهارات الزراعة وريادة الأعمال"),
    ("drama_p4_t1", r"الصف-الرابع\الترم-الأول\التربية-المسرحية\كتاب-الطالب\4ب-مسرح-وزارة-كتاب-2027.pdf",
     "التربية_المسرحية_الصف_الرابع_الابتدائي_ت1", 51, "التربية المسرحية"),
    ("math_p2_t1", r"الصف-الثاني\الترم-الأول\الرياضيات\كتاب-الطالب\2ب-ماث-وزارة-كتاب-2027.pdf",
     "الرياضيات_الصف_الثاني_الابتدائي_ت1", 128, "الرياضيات"),
    # ---------------- الصف الخامس (الأثقل) ----------------
    ("family_skills_p5_t1", r"الصف-الخامس\الترم-الأول\مهارات-إدارة-الأسرة-وريادة-الأعمال\كتاب-الطالب\5ب-مهارات-أسرة-وزارة-كتاب-2027.pdf",
     "مهارات_إدارة_الأسرة_الصف_الخامس_الابتدائي_ت1", 56, "مهارات إدارة الأسرة وريادة الأعمال"),
    ("drama_p5_t1", r"الصف-الخامس\الترم-الأول\التربية-المسرحية\كتاب-الطالب\5ب-مسرح-وزارة-كتاب-2027.pdf",
     "التربية_المسرحية_الصف_الخامس_الابتدائي_ت1", 63, "التربية المسرحية"),
    ("religion_islamic_p5_t1", r"الصف-الخامس\الترم-الأول\التربية-الدينية-الإسلامية\كتاب-الطالب\5ب-تدين-اسلامي-وزارة-كتاب-2027.pdf",
     "التربية_الدينية_الإسلامية_الصف_الخامس_الابتدائي_ت1", 96, "التربية الدينية الإسلامية"),
    ("studies_p5_t1", r"الصف-الخامس\الترم-الأول\الدراسات-الاجتماعية\كتاب-الطالب\5ب-دراسات-وزارة-كتاب-2027.pdf",
     "الدراسات_الاجتماعية_الصف_الخامس_الابتدائي_ت1", 98, "الدراسات الاجتماعية"),
    ("religion_islamic_p4_t1", r"الصف-الرابع\الترم-الأول\التربية-الدينية-الإسلامية\كتاب-الطالب\4ب-تدين-اسلامي-وزارة-كتاب-2027.pdf",
     "التربية_الدينية_الإسلامية_الصف_الرابع_الابتدائي_ت1", 98, "التربية الدينية الإسلامية"),
    # ---------------- الصف السادس ----------------
    ("library_skills_p6_t1", r"الصف-السادس\الترم-الأول\المكتبات-ومهارات-البحث\كتاب-الطالب\6ب-مكتبات-وزارة-كتاب-2027.pdf",
     "المكتبات_ومهارات_البحث_الصف_السادس_الابتدائي_ت1", 42, "المكتبات ومهارات البحث"),
    ("agriculture_skills_p6_t1", r"الصف-السادس\الترم-الأول\مهارات-الزراعة-وريادة-الأعمال\كتاب-الطالب\6ب-مهارات-زراعة-وزارة-كتاب-2027.pdf",
     "مهارات_الزراعة_الصف_السادس_الابتدائي_ت1", 41, "مهارات الزراعة وريادة الأعمال"),
    ("ict_p6_t1", r"الصف-السادس\الترم-الأول\تكنولوجيا-المعلومات-والاتصالات\كتاب-الطالب\6ب-تكنولوجيا-وزارة-كتاب-2027.pdf",
     "تكنولوجيا_المعلومات_والاتصالات_الصف_السادس_الابتدائي_ت1", 57, "تكنولوجيا المعلومات والاتصالات"),
    ("family_skills_p6_t1", r"الصف-السادس\الترم-الأول\مهارات-إدارة-الأسرة-وريادة-الأعمال\كتاب-الطالب\6ب-مهارات-أسرة-وزارة-كتاب-2027.pdf",
     "مهارات_إدارة_الأسرة_الصف_السادس_الابتدائي_ت1", 52, "مهارات إدارة الأسرة وريادة الأعمال"),
    ("media_edu_p6_t1", r"الصف-السادس\الترم-الأول\الإعلام-التربوي\كتاب-الطالب\6ب-اعلام-وزارة-كتاب-2027.pdf",
     "الإعلام_التربوي_الصف_السادس_الابتدائي_ت1", 63, "الإعلام التربوي"),
    ("religion_islamic_p6_t1", r"الصف-السادس\الترم-الأول\التربية-الدينية-الإسلامية\كتاب-الطالب\6ب-تدين-اسلامي-وزارة-كتاب-2027.pdf",
     "التربية_الدينية_الإسلامية_الصف_السادس_الابتدائي_ت1", 98, "التربية الدينية الإسلامية"),
    ("science_p6_t1", r"الصف-السادس\الترم-الأول\العلوم\كتاب-الطالب\6ب-علوم-وزارة-كتاب-2027.pdf",
     "العلوم_الصف_السادس_الابتدائي_ت1", 98, "العلوم"),
    ("studies_p6_t1", r"الصف-السادس\الترم-الأول\الدراسات-الاجتماعية\كتاب-الطالب\6ب-دراسات-وزارة-كتاب-2027.pdf",
     "الدراسات_الاجتماعية_الصف_السادس_الابتدائي_ت1", 114, "الدراسات الاجتماعية"),
    ("math_p6_t1", r"الصف-السادس\الترم-الأول\الرياضيات\كتاب-الطالب\6ب-ماث-وزارة-كتاب-2027.pdf",
     "الرياضيات_الصف_السادس_الابتدائي_ت1", 122, "الرياضيات"),
]

GRADE_WORD = {
    "الدراسات_الاجتماعية": "الدراسات الاجتماعية",
}

_lock = threading.Lock()

try:  # وحدة التحكم على ويندوز قد تكون cp1256
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with _lock:
        print(line, flush=True)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def run(cmd: list[str]) -> int:
    """ينفّذ أمرًا ويُرجع رمز الخروج مع تسجيل مخرجات مختصرة."""
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        tail = (p.stdout or "")[-500:] + (p.stderr or "")[-500:]
        log(f"    ↳ تحذير (code {p.returncode}): {tail.strip()[:400]}")
    return p.returncode


def resolve_src(rel: str) -> Path:
    """مسار PDF: مسار يبدأ بمجلد مرحلة يُحسب من جذر المكتبة، وإلا من الابتدائي."""
    return (LIB / rel) if rel.startswith(STAGE_DIRS) else (SRC / rel)


def registered_ids() -> set[str]:
    """معرّفات الكتب المسجَّلة فعليًّا في catalog.yaml (لتخطّي إعادة التسجيل)."""
    cat = ROOT / "meta" / "catalog.yaml"
    if not cat.exists():
        return set()
    return {ln.strip()[6:].strip() for ln in cat.read_text(encoding="utf-8").splitlines()
            if ln.strip().startswith("- id: ")}


def book_title(book: str, subject: str) -> str:
    """«المادة — الصف … — الفصل الدراسي الأول» للمراحل الثلاث."""
    if "_الصف_" in book:
        after = book.split("_الصف_", 1)[1]
        for w in STAGE_WORDS:
            if f"_{w}_" in after:
                grade = after.split(f"_{w}_", 1)[0]
                return f"{subject} — الصف {grade} {w} — الفصل الدراسي الأول"
    return f"{subject} — {book}"


def pdf_pages_files(book: str) -> dict[int, Path]:
    d = OUT / book
    res: dict[int, Path] = {}
    if not d.is_dir():
        return res
    for f in d.glob("page_*.md"):
        try:
            res[int(f.stem.split("_")[1])] = f
        except (IndexError, ValueError):
            continue
    return res


def process(entry: tuple[str, str, str, int, str]) -> str:
    book_id, rel, book, total, subject = entry
    t0 = time.time()
    log(f"▶ بدء {book_id} ({total} صفحة)")

    # 1) نسخ PDF
    src = resolve_src(rel)
    dst = RAW / f"{book}.pdf"
    if not src.exists():
        log(f"✗ {book_id}: المصدر غير موجود {src}")
        return f"{book_id}: فشل (لا مصدر)"
    if not dst.exists():
        shutil.copy2(src, dst)

    # 2) رسم الصور
    run([sys.executable, "scripts/convert/render_book_images.py", "--book", book])

    # 3) التفريغ (يستأنف لا يعيد)
    run([sys.executable, "scripts/convert/run_vision_batch.py", "--book", book,
         "--start", "1", "--end", str(total), "--workers", str(VISION_WORKERS)])

    # 4) إعادة الصفحات الناقصة/الفارغة
    for rnd in range(1, MAX_RETRY_ROUNDS + 1):
        files = pdf_pages_files(book)
        bad = [n for n in range(1, total + 1)
               if n not in files or files[n].stat().st_size == 0]
        if not bad:
            break
        log(f"  ↻ {book_id}: جولة إصلاح {rnd} — {len(bad)} صفحة")
        for n in bad:
            f = files.get(n)
            if f is not None:
                f.unlink(missing_ok=True)
            run([sys.executable, "scripts/convert/run_vision_batch.py", "--book", book,
                 "--start", str(n), "--end", str(n), "--workers", "1"])

    files = pdf_pages_files(book)
    missing = [n for n in range(1, total + 1) if n not in files]
    if missing:
        log(f"⚠ {book_id}: بقي {len(missing)} صفحة ناقصة {missing[:10]} — يُسجَّل مع ملاحظة")

    # 5) فحص الجودة
    lam = 0
    for f in files.values():
        try:
            if "األ" in f.read_text(encoding="utf-8") or "اإل" in f.read_text(encoding="utf-8"):
                lam += 1
        except OSError:
            pass

    # 6) التسجيل (يُتخطّى إن كان مسجَّلًا — للاستئناف بعد توقف)
    title = book_title(book, subject)
    if book_id in registered_ids():
        log(f"  ⏭ {book_id}: مسجَّل مسبقًا — تجاوز التسجيل")
    else:
        rc = run([sys.executable, "scripts/retrieval/onboard_book.py", "--book", book,
                  "--id", book_id, "--title", title, "--author", AUTHOR,
                  "--publisher", PUBLISHER, "--subject", subject])
        if rc != 0:
            log(f"✗ {book_id}: فشل التسجيل")
            return f"{book_id}: فشل التسجيل"

    # 7) الخريطة
    run([sys.executable, "scripts/retrieval/toc_review.py", "--book", book_id])

    mins = (time.time() - t0) / 60
    log(f"✓ تم {book_id}: {len(files)}/{total} صفحة | لام-ألف {lam} | {mins:.0f} دقيقة")
    return f"{book_id}: {len(files)}/{total} (لام-ألف {lam})"


def run_guard() -> int:
    """يشغّل حارس مساحة العمل (scripts/validate_all.py) ويعيد رمز خروجه."""
    script = ROOT / "scripts" / "validate_all.py"
    if not script.exists():
        return 0
    sys.stdout.flush()  # حتى تظهر مخرجات الحارس بترتيبها لا قبل مخرجات الأب
    return subprocess.run([sys.executable, str(script), "--quiet"], cwd=str(ROOT)).returncode


def main() -> int:
    queue = QUEUE
    if "--queue" in sys.argv:
        import json

        path = Path(sys.argv[sys.argv.index("--queue") + 1])
        queue = [tuple(e) for e in json.loads(path.read_text(encoding="utf-8"))]
    log("=" * 60)
    log(f"بدء التفريغ الشامل: {len(queue)} كتابًا | تزامن {MAX_PARALLEL_BOOKS}")
    results: list[str] = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_BOOKS) as ex:
        futs = {ex.submit(process, e): e for e in queue}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                e = futs[fut]
                log(f"✗ انهيار {e[0]}: {exc}")
                results.append(f"{e[0]}: انهيار")

    run([sys.executable, "scripts/retrieval/toc_review.py", "--validate"])
    guard_rc = run_guard()
    log("-" * 60)
    for r in results:
        log("   " + r)
    log("انتهى التفريغ الشامل.")
    return guard_rc


if __name__ == "__main__":
    sys.exit(main())
