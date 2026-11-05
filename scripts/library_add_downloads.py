# -*- coding: utf-8 -*-
"""
إضافة كتب اللغة العربية من مجلد التنزيلات إلى المكتبة التعليمية.

المصدر  (قراءة فقط): C:\\Users\\blals\\Downloads\\Arabic-T1-2026-2027
الهدف   (كتابة)    : D:\\المكتبة-التعليمية\\01-كتب-مدرسية و 05-تقييمات

ما يفعله:
  1) ينسخ كل ملف إلى مساره المعتمد باسم موحّد <صف>-<مادة>-<مصدر>-<نوع>-<سنة>.pdf
  2) يحسب SHA256 وعدد الصفحات والحجم
  3) يُسجّل كل كتاب في _الفهرس.yaml ويحدّث counts
  4) لا يحذف شيئًا من المصدر ولا من المكتبة

التشغيل: python scripts/library_add_downloads.py
"""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import fitz  # pymupdf

SRC = Path(r"C:\Users\blals\Downloads\Arabic-T1-2026-2027")
LIB = Path(r"D:\المكتبة-التعليمية")
INDEX = LIB / "_الفهرس.yaml"
REPORT = Path(__file__).resolve().parents[1] / "logs" / "library_add_downloads.json"

YEAR = 2027
SUBJECT = "اللغة-العربية"

# (ملف المصدر, المرحلة, الصف, الرمز, workspace_id)
STUDENT_BOOKS = [
    ("StudentBook/01-Primary/Arabic-G1-Primary-T1-StudentBook.pdf", "1-ابتدائي", "الصف-الأول", "1ب", "arabic_p1_t1"),
    ("StudentBook/01-Primary/Arabic-G2-Primary-T1-StudentBook.pdf", "1-ابتدائي", "الصف-الثاني", "2ب", "arabic_p2_t1"),
    ("StudentBook/01-Primary/Arabic-G3-Primary-T1-StudentBook.pdf", "1-ابتدائي", "الصف-الثالث", "3ب", "arabic_p3_t1"),
    ("StudentBook/01-Primary/Arabic-G4-Primary-T1-StudentBook.pdf", "1-ابتدائي", "الصف-الرابع", "4ب", "arabic_p4_t1"),
    ("StudentBook/01-Primary/Arabic-G5-Primary-T1-StudentBook.pdf", "1-ابتدائي", "الصف-الخامس", "5ب", "arabic_p5_t1"),
    ("StudentBook/01-Primary/Arabic-G6-Primary-T1-StudentBook.pdf", "1-ابتدائي", "الصف-السادس", "6ب", "arabic_p6_t1"),
    ("StudentBook/02-Preparatory/Arabic-G7-Preparatory-T1-StudentBook.pdf", "2-إعدادي", "الصف-الأول", "1ع", "arabic_prep1_t1"),
    ("StudentBook/02-Preparatory/Arabic-G8-Preparatory-T1-StudentBook.pdf", "2-إعدادي", "الصف-الثاني", "2ع", "arabic_prep2_t1"),
    ("StudentBook/02-Preparatory/Arabic-G9-Preparatory-T1-StudentBook.pdf", "2-إعدادي", "الصف-الثالث", "3ع", "arabic_prep3_t1"),
    ("StudentBook/03-Secondary/Arabic-S1-First-T1-StudentBook.pdf", "3-ثانوي", "الصف-الأول", "1ث", "arabic_sec1_t1"),
    ("StudentBook/03-Secondary/Arabic-S2-Second-T1-StudentBook.pdf", "3-ثانوي", "الصف-الثاني", "2ث", "arabic_sec2_t1"),
    ("StudentBook/03-Secondary/Arabic-S3-Third-T1-StudentBook.pdf", "3-ثانوي", "الصف-الثالث", "3ث", "arabic_sec3_t1"),
]

PENDING_WS = {"arabic_sec2_t1", "arabic_sec3_t1"}

TERM = "الترم-الأول"
GRADE_NAME = {
    "1ب": "الصف الأول الابتدائي", "2ب": "الصف الثاني الابتدائي", "3ب": "الصف الثالث الابتدائي",
    "4ب": "الصف الرابع الابتدائي", "5ب": "الصف الخامس الابتدائي", "6ب": "الصف السادس الابتدائي",
    "1ع": "الصف الأول الإعدادي", "2ع": "الصف الثاني الإعدادي", "3ع": "الصف الثالث الإعدادي",
    "1ث": "الصف الأول الثانوي", "2ث": "الصف الثاني الثانوي", "3ث": "الصف الثالث الثانوي",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pages(path: Path) -> int:
    try:
        with fitz.open(path) as doc:
            return doc.page_count
    except Exception:
        return 0


def q(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def entry(book_id, title, stage, grade, subject, source, kind, year, rel_path,
          page_count, size_mb, digest, status, workspace_id, notes):
    lines = [
        f'  - id: {q(book_id)}',
        f'    title: {q(title)}',
        f'    stage: {q(stage)}',
        f'    grade: {q(grade)}',
        f'    term: {q(TERM)}',
        f'    subject: {q(subject)}',
        f'    source: {q(source)}',
        f'    type: {q(kind)}',
        f'    year: {year}',
        f'    path: {q(rel_path)}',
        f'    pages: {page_count}',
        f'    size_mb: {size_mb}',
        f'    sha256: {q(digest)}',
        f'    status: {q(status)}',
        f'    workspace_id: {q(workspace_id) if workspace_id else "null"}',
        f'    notes: {q(notes)}',
    ]
    return "\n".join(lines)


def main() -> int:
    if not SRC.is_dir():
        print(f"المصدر غير موجود: {SRC}")
        return 1

    books = []
    report = []

    def process(src_rel, stage, grade, subject, source, kind, year, code, suffix="", ws=None):
        src = SRC / src_rel
        if not src.is_file():
            print(f"! مفقود: {src_rel}")
            return
        folder = LIB / "01-كتب-مدرسية" if source == "وزارة" and kind in ("كتاب", "أنشطة") \
            else LIB / "05-تقييمات"
        if folder.name == "01-كتب-مدرسية":
            dest_dir = folder / stage / grade / TERM / subject / f"كتاب-{'الطالب' if kind == 'كتاب' else 'الأنشطة'}"
        else:
            dest_dir = folder / stage / grade / TERM / subject
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = f"{code}-عربي-{source}-{kind}{suffix}-{year}.pdf"
        dest = dest_dir / name

        digest = sha256(src)
        if dest.is_file() and sha256(dest) == digest:
            action = "موجود"
        else:
            shutil.copy2(src, dest)
            action = "نُسخ"

        pc = pages(dest)
        size_mb = round(dest.stat().st_size / (1024 * 1024), 1)
        status = "تالف" if pc == 0 else ("مستخدم" if ws and ws not in PENDING_WS else "مرشح")
        if pc == 0:
            notes = "لا يُفتح — 0 صفحة"
        elif ws in PENDING_WS:
            notes = "حُوِّل نصيًّا في الـworkspace، بانتظار التسجيل في meta/catalog.yaml"
        elif ws:
            notes = ""
        else:
            notes = "أوراق تقييم — ترم أول"
        if kind == "تقييم" and not suffix:
            notes = "ملف تقييمات الترم الأول كاملًا لصف واحد" if pc else notes

        book_id = f"{code}-عربي-{source}-{kind}{suffix}"
        title = f"اللغة العربية — {GRADE_NAME[code]} — الترم الأول — " + (
            "كتاب الطالب" if kind == "كتاب" else
            ("أوراق التقييم" if kind == "تقييم" else kind))
        rel = dest.relative_to(LIB).as_posix()
        books.append(entry(book_id, title, stage, grade, subject, source, kind, year,
                           rel, pc, size_mb, digest, status, ws, notes))
        report.append({"id": book_id, "path": rel, "pages": pc, "size_mb": size_mb,
                       "sha256": digest, "status": status, "action": action})
        print(f"{action:<6} {pc:>3} صفحة  {size_mb:>7} MB  {rel}")

    for src_rel, stage, grade, code, ws in STUDENT_BOOKS:
        process(src_rel, stage, grade, "اللغة-العربية", "وزارة", "كتاب", YEAR, code, "", ws)

    for i in range(1, 7):
        stage = "1-ابتدائي"
        grade = ["الصف-الأول", "الصف-الثاني", "الصف-الثالث", "الصف-الرابع", "الصف-الخامس", "الصف-السادس"][i - 1]
        process(f"Assessments/01-Primary/Arabic-G{i}-Primary-T1-Assessments.pdf",
                stage, grade, "اللغة-العربية", "وزارة", "تقييم", YEAR, f"{i}ب")

    for i, code, grade in [(7, "1ع", "الصف-الأول"), (8, "2ع", "الصف-الثاني"), (9, "3ع", "الصف-الثالث")]:
        process(f"Assessments/02-Preparatory/Arabic-G{i}-Preparatory-T1-Assessments.pdf",
                "2-إعدادي", grade, "اللغة-العربية", "وزارة", "تقييم", YEAR, code)

    for grade, code, idx in [("الصف-الأول", "1ث", 1), ("الصف-الثاني", "2ث", 2)]:
        for week in range(1, 8):
            process(f"Assessments/03-Secondary/Arabic-Sec{idx}-T1-Week{week}-Assessment.pdf",
                    "3-ثانوي", grade, "اللغة-العربية", "وزارة", "تقييم", YEAR, code, f"-أ{week:02d}")

    # ---- تحديث _الفهرس.yaml
    text = INDEX.read_text(encoding="utf-8")
    head, sep, tail = text.partition("\nbooks: []\n")
    if not sep:
        print("! لم أجد سطر `books: []` في الفهرس — أُلغي التحديث")
        return 2
    block = "books:\n" + "\n\n".join(books) + "\n"
    text = head + "\n" + block + tail

    counts = {"total": len(report), "مستخدم": 0, "مرشح": 0, "تالف": 0, "مكرر": 0}
    for item in report:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    for key, value in counts.items():
        text = re.sub(rf"(?m)^(\s+{re.escape(key)}: )\d+$", rf"\g<1>{value}", text, count=1)
    text = re.sub(r'(?m)^updated: .*$', 'updated: "2026-10-31"', text, count=1)
    INDEX.write_text(text, encoding="utf-8")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"counts": counts, "books": report}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"\ncounts={counts}\nتقرير: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
