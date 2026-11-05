#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
onboard_book.py — تسجيل كتاب محوَّل في طبقة الاسترجاع (Onboarding).

الغرض:
    بعد اكتمال تحويل كتاب جديد إلى output/<book>/page_XXX.md، هذا السكريبت
    ينفّذ الخطوات الميكانيكية لتسجيله كي يصبح قابلًا للبحث:
      1. التحقق من وجود المخرجات وحساب الإحصاءات (عدد الصفحات، الفجوات، الصور، PDF).
      2. إضافة مدخل للكتاب في meta/catalog.yaml (بانتظام، وبلا تكرار).
      3. بناء فهرسه المعجمي عبر build_index.build_book() (نفس منطق الفهرس الموحّد).
      4. توليد مسوّدة خريطة موضوعات meta/books/<id>/toc.draft.yaml من عناوين الكتاب.

ما يقرأه:
    output/<book>/page_XXX.md            (المخرجات)
    curriculum_raw/<book>_images/         (صور الصفحات — للعدّ فقط)
    curriculum_raw/<book>.pdf             (إن وُجد)
    meta/catalog.yaml                     (للتحقق من عدم التكرار)

ما يكتبه:
    meta/catalog.yaml                     (إضافة مدخل الكتاب)
    index/<book>/...                      (عبر build_index)
    meta/books/<id>/toc.draft.yaml        (مسوّدة — تحتاج مراجعة بشرية)

ملاحظات:
    - لا يمسّ curriculum/ ولا output/ إطلاقًا (قراءة فقط).
    - مكتبات بايثون المعيارية فقط.
    - المسوّدة تبقى `.draft` عمدًا كي لا تُستخدم قبل المراجعة والاعتماد
      (أعد تسميتها إلى toc.yaml بعد التنقيح، وأضف keywords).

الاستخدام:
    python scripts/onboard_book.py --book "كيف_تتقن_الصرف" --id sarf \
        --title "كيف تتقن الصرف؟" --author "أحمد إسكندر" --subject "الصرف" \
        --publisher "دار اللؤلؤة للنشر والتوزيع — المنصورة، مصر"

    # اختبار بلا كتابة:
    python scripts/onboard_book.py --book "كيف_تتقن_النحو" --id nahw --dry-run
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# حماية الطباعة من انهيار cp1256 على الأحرف ✓/✗ (Windows — كونسول عربي)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_index import WORKSPACE, OUTPUT_DIR, INDEX_DIR, build_book, normalize  # noqa: E402

CATALOG = WORKSPACE / "meta" / "catalog.yaml"
META_BOOKS = WORKSPACE / "meta" / "books"
RAW_DIR = WORKSPACE / "curriculum_raw"

# بداية قسم المصادر الخارجية في catalog.yaml — يُدرج مدخل الكتاب قبله.
EXTERNAL_MARKER = "# المصادر الخارجية"

# عناوين لا تصلح مدخلات في خريطة الموضوعات (تمارين وملخصات وتكرارات).
NOISE_RE = re.compile(
    r"تدريب|الإجابة|الإجَابَة|مُلَخَّص|ملخص|مَلْخَص|ملكص|تأكد|تأكّد|الخلاصة|الْخُلَاصَة|"
    r"كيف (?:تُتْقِن|تتقن|تُلَقِّن|تلقن|تُلْقِن|تقرأ|تُقْرَى|تفهم|تُفْهَم|تهندس|نُتقن|نتقن)"
)

# بداية فصل جديد: «الفصل الأول»، «الباب الثالث»...
CHAPTER_RE = re.compile(r"^\s*(?:ال)?(?:فصل|فَصْل|باب|بَاب|الْفَصْل|الْبَاب)\b", re.UNICODE)


# ------------------------------------------------------------------ مساعدات
def q(value: str) -> str:
    """يقتبس نصًّا لـ YAML (سلسلة بين علامتَي تنصيص).

    عناوين OCR تحمل هروب Markdown مثل `\\*`، وهو ليس هروبًا صالحًا في YAML،
    فيُفكّ الهروب أولًا ثم يُهرَّب الشرطة العكسية المتبقية.
    """
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!])", r"\1", value or "")
    return '"' + text.replace("\\", "\\\\").replace('"', "'").replace("\n", " ") + '"'


def read_catalog() -> str:
    return CATALOG.read_text(encoding="utf-8") if CATALOG.exists() else ""


def id_exists(catalog_text: str, book_id: str) -> bool:
    return re.search(rf"^\s*-\s*id:\s*{re.escape(book_id)}\s*$", catalog_text, re.M) is not None


def count_images(book: str) -> int:
    d = RAW_DIR / f"{book}_images"
    return len(list(d.glob("*.png"))) + len(list(d.glob("*.jpg"))) if d.exists() else 0


def find_pdf(book: str) -> Path | None:
    p = RAW_DIR / f"{book}.pdf"
    return p if p.exists() else None


def page_numbers(book_dir: Path) -> list[int]:
    nums = []
    for f in book_dir.glob("page_*.md"):
        m = re.fullmatch(r"page_(\d+)\.md", f.name)
        if m:
            nums.append(int(m.group(1)))
    return sorted(nums)


def catalog_block(args, pages_total: int, converted: int, missing: list[int], has_pdf: bool) -> str:
    pdf_line = f'"curriculum_raw/{args.book}.pdf"' if has_pdf else "null"
    missing_txt = "[" + ", ".join(str(x) for x in missing) + "]"
    note = "اكتمل التحويل" if not missing else f"ناقص {len(missing)} صفحة"
    return f"""
  - id: {args.id}
    title: {q(args.title)}
    title_normalized: {q(normalize(args.title))}
    author: {q(args.author)}
    publisher: {q(args.publisher or "غير موثّق في الملفات المتاحة")}
    subject: {q(args.subject)}
    notes: {q(args.notes or "")}

    source_pdf: {pdf_line}
    source_images: "curriculum_raw/{args.book}_images"
    text_dir: "output/{args.book}"
    index_dir: "index/{args.book}/norm"
    toc: "meta/books/{args.id}/toc.yaml"

    pages_total: {pages_total}
    pages_converted: {converted}
    missing_pages: {missing_txt}
    status: {"converted" if not missing else "partial"}
    status_note: "{note}: {converted}/{pages_total}."
"""


def insert_into_catalog(block: str) -> None:
    """يُدرج مدخل الكتاب قبل قسم المصادر الخارجية (أو في نهاية الملف)."""
    text = read_catalog()
    idx = text.find(EXTERNAL_MARKER)
    if idx == -1:
        new_text = text.rstrip("\n") + "\n" + block
    else:
        new_text = text[:idx].rstrip("\n") + "\n" + block + "\n" + text[idx:]
    CATALOG.write_text(new_text, encoding="utf-8")


# ------------------------------------------------------------------ مسوّدة TOC
def toc_draft(book_dir: Path, book_id: str, title: str) -> str:
    """يبني مسوّدة خريطة موضوعات من headings_draft.tsv المولّد من build_index."""
    draft = INDEX_DIR / book_dir.name / "headings_draft.tsv"
    rows: list[tuple[int, int, str]] = []
    if draft.exists():
        for line in draft.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            page, level, text = int(parts[0]), int(parts[1]), parts[2].strip()
            if not text or NOISE_RE.search(normalize(text)):
                continue
            rows.append((page, level, text))

    rows.sort()
    chapters: list[dict] = []
    for page, level, text in rows:
        if level == 1 and CHAPTER_RE.match(text):
            chapters.append({"title": text, "from": page, "topics": []})
        elif chapters and level in (1, 2):
            # السطور الغامقة القصيرة (level 0) تُستبعد: غالبًا أسماء وترويسات لا مواضيع.
            chapters[-1]["topics"].append({"title": text, "page": page})
        elif not chapters and level in (1, 2):
            chapters.append({"title": "مقدمة", "from": page, "topics": [{"title": text, "page": page}]})

    # إغلاق نطاقات الفصول: to = ما قبل الفصل التالي.
    for i, ch in enumerate(chapters):
        ch["to"] = (chapters[i + 1]["from"] - 1) if i + 1 < len(chapters) else (
            max([p for p, _, _ in rows], default=ch["from"]) if rows else ch["from"]
        )

    out = [
        "# ============================================================================",
        f"# خريطة موضوعات (مسوّدة): {title}",
        "# ----------------------------------------------------------------------------",
        "# حُدِّدت آليًّا من عناوين Markdown — تحتاج مراجعة بشرية:",
        "#   1. احذف المدخلات غير الدالة، وأضف keywords لهذه الفصول.",
        "#   2. أعد تسمية الملف إلى toc.yaml وحدّث قيم reviewed.",
        "# الصفحات أرقام ملفات (page_XXX.md) لا أرقام المطبوع.",
        "# ============================================================================",
        "",
        f"book_id: {book_id}",
        f"title: {q(title)}",
        f'text_dir: "output/{book_dir.name}"',
        f'index_dir: "index/{book_dir.name}/norm"',
        f"reviewed: false",
        f'derived_from: "index/{book_dir.name}/headings_draft.tsv"',
        "",
        "chapters:",
    ]
    for ch in chapters:
        out.append(f"  - title: {q(ch['title'])}")
        out.append(f"    from: {ch['from']}")
        out.append(f"    to: {ch['to']}")
        if ch["topics"]:
            out.append("    topics:")
            for tp in ch["topics"]:
                out.append(f"      - {{ title: {q(tp['title'])}, page: {tp['page']} }}")
        else:
            out.append("    topics: []")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ التشغيل
def run_guard() -> int:
    """يشغّل حارس مساحة العمل (scripts/validate_all.py) ويعيد رمز خروجه."""
    script = WORKSPACE / "scripts" / "validate_all.py"
    if not script.exists():
        return 0
    sys.stdout.flush()  # حتى تظهر مخرجات الحارس بترتيبها لا قبل مخرجات الأب
    return subprocess.run([sys.executable, str(script), "--quiet"], cwd=str(WORKSPACE)).returncode


def main() -> int:
    p = argparse.ArgumentParser(description="تسجيل كتاب محوَّل في طبقة الاسترجاع")
    p.add_argument("--book", required=True, help="اسم مجلد الكتاب في output/ (عربي)")
    p.add_argument("--id", required=True, help="معرّف لاتيني قصير (balagha, nahw, sarf…)")
    p.add_argument("--title", required=True)
    p.add_argument("--author", default="غير موثّق")
    p.add_argument("--subject", default="")
    p.add_argument("--publisher", default="")
    p.add_argument("--notes", default="")
    p.add_argument("--dry-run", action="store_true", help="فحص فقط بلا كتابة أي ملف")
    args = p.parse_args()

    book_dir = OUTPUT_DIR / args.book
    if not book_dir.is_dir():
        print(f"[✗] لا يوجد مجلد مخرجات: output/{args.book}")
        return 1

    nums = page_numbers(book_dir)
    if not nums:
        print(f"[✗] لا توجد ملفات page_XXX.md في output/{args.book}")
        return 1

    highest = nums[-1]
    missing = [n for n in range(1, highest + 1) if n not in set(nums)]
    images = count_images(args.book)
    pdf = find_pdf(args.book)
    catalog_text = read_catalog()

    print("=" * 64)
    print(f"[i] الكتاب: {args.book}  (id: {args.id})")
    print(f"    صفحات محوَّلة: {len(nums)} | أقصى صفحة: {highest} | فجوات: {len(missing)}")
    if missing:
        print(f"    فجوات: {missing[:10]}{' …' if len(missing) > 10 else ''}")
    print(f"    صور متاحة: {images} | PDF: {'نعم' if pdf else 'لا'}")
    print(f"    مسجَّل في catalog.yaml: {'نعم' if id_exists(catalog_text, args.id) else 'لا'}")

    if id_exists(catalog_text, args.id):
        print(f"[!] المعرّف «{args.id}» موجود مسبقًا في catalog.yaml — لا تكرار.")
        print("    (لتحديث كتاب قائم، عدّل مدخله يدويًّا أو احذفه ثم أعد التشغيل.)")
        return 2

    if args.dry_run:
        print("[i] وضع الفحص فقط — لم يُكتب أي ملف.")
        print("=" * 64)
        return 0

    # 1) سجل الكتاب في الفهرس
    insert_into_catalog(catalog_block(args, highest, len(nums), missing, bool(pdf)))
    print(f"[✓] أُضيف المدخل إلى meta/catalog.yaml")

    # 2) بناء الفهرس المعجمي
    m = build_book(book_dir)
    print(f"[✓] بُني الفهرس: {m['pages_indexed']} صفحة | {m['normalized_chars']:,} حرفًا مُطبَّعًا")

    # 3) مسوّدة خريطة الموضوعات
    dest = META_BOOKS / args.id
    dest.mkdir(parents=True, exist_ok=True)
    draft_path = dest / "toc.draft.yaml"
    draft_path.write_text(toc_draft(book_dir, args.id, args.title), encoding="utf-8")
    print(f"[✓] كُتبت المسوّدة: meta/books/{args.id}/toc.draft.yaml")

    print("-" * 64)
    print("[i] الخطوات المتبقية (بشرية):")
    print("    1. راجع المسوّدة، احذف غير الدالّ، أضف keywords، ثم أعد تسميتها toc.yaml.")
    print("    2. سجّل العملية في scripts/execution_log.md.")
    print("    (لا تُحدَّث قائمة معرّفات في أي مهارة: meta/catalog.yaml هو المصدر الوحيد.)")
    print("=" * 64)
    # 4) الحارس: كتاب جديد بلا toc.yaml أو بعدّ خاطئ يفشل هنا بصوت عالٍ
    return run_guard()


if __name__ == "__main__":
    sys.exit(main())
