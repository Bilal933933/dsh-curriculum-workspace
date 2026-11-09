#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_index.py — بناء طبقة الفهرسة المعجمية لكتب المنهج المحوَّلة.

الغرض:
    الكتب المحوَّلة في output/<book>/page_XXX.md نصٌّ عربي مُشكَّل بالكامل،
    والبحث الخام عن «الاستعارة» لا يطابق «الِاسْتِعَارَة». هذا السكريبت يُنتج
    نسخًا مُطبَّعة (بلا تشكيل ولا فروق إملائية) تصلح لبحث grep سريع ودقيق،
    مع الحفاظ على الربط الأصلي: كل ملف مطبَّع يقابل صفحة أصلية واحدة.

ما يقرأه (قراءة فقط):
    output/<book>/page_XXX.md

ما يكتبه (داخل مساحة العمل فقط):
    index/<book>/norm/page_XXX.txt      نص الصفحة مُطبَّعًا
    index/<book>/manifest.json          خريطة الصفحات + الفجوات + الأحجام
    index/<book>/headings_draft.tsv     مسوّدة عناوين الفصول للمراجعة البشرية

سياسة:
    - لا يمسّ curriculum/ ولا output/ إطلاقًا.
    - مكتبات بايثون المعيارية فقط (لا .venv ولا تثبيتات).
    - إعادة التشغيل آمنة: المخرجات مشتقة وقابلة للتوليد من جديد.

الاستخدام:
    python scripts/build_index.py
    python scripts/build_index.py --book "كيف_تتقن_البلاغة"
    python scripts/build_index.py --dry-run          # فحص بلا كتابة
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = WORKSPACE / "output"
INDEX_DIR = WORKSPACE / "index"
CATALOG = WORKSPACE / "meta" / "catalog.yaml"

# وحدة تحكّم ويندوز قد تكون cp1256 فلا تُرمِّز ✓ — نحوّل المخرجات إلى UTF-8 بدل الانهيار.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def printed_page_offset(book_name: str) -> int | str:
    """إزاحة الصفحة المطبوعة عن رقم الملف، من catalog.yaml ("unknown" إن لم تُعرف).

    الاستشهاد يطبع الرقمين عند المعرفة: «ص ٣١٦ (ملف page_317)».
    """
    if not CATALOG.exists():
        return "unknown"
    for chunk in re.split(r"\n  - id: ", CATALOG.read_text(encoding="utf-8-sig"))[1:]:
        if f'text_dir: "output/{book_name}"' in chunk:
            m = re.search(r"^    printed_page_offset: (\S+)$", chunk, re.M)
            if not m:
                return "unknown"
            raw = m.group(1)
            return int(raw) if re.fullmatch(r"-?\d+", raw) else "unknown"
    return "unknown"

# ---------------------------------------------------------------- التطبيع

# التشكيل وعلامات الضبط والتطويل والرموز القرآنية.
TASHKEEL_RE = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")

# توحيد الحروف: فروق إملائية لا تغيّر الكلمة عند البحث.
LETTER_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي", "ؤ": "و",
    "ة": "ه",
})

# الأرقام الهندية والفارسية إلى لاتينية.
DIGIT_MAP = str.maketrans({**{chr(0x0660 + i): str(i) for i in range(10)},
                           **{chr(0x06F0 + i): str(i) for i in range(10)}})

# كل ما ليس حرفًا (عربيًّا أو لاتينيًّا) أو رقمًا أو شرطة سفلية أو مسافة يصبح مسافة.
# \w في بايثون يغطّي الحروف العربية والأرقام أصلًا؛ فإضافة نطاق \u0600-\u06FF كانت
# تُعيد إدخال علامات الترقيم العربية (، ؛ ؟ ٪) فتختلف نتائج المطابقة بين نصّين متطابقين معنى.
NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)

# ترويسة الصفحة الجارية: "49 | **كَيْفَ تُقِنُّ البَلَاغَةَ؟**"
RUNNING_HEADER_RE = re.compile(r"^\s*[\d\u0660-\u0669]+\s*\|\s*")

# سطر عنوان مرشَّح: سطر بالكامل غامق وقصير.
BOLD_LINE_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")

# عنوان Markdown: من # إلى ###.
MD_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")

# ترويسات الصفحات التي التقطها التحويل كعناوين — تُستبعد من مسوّدة الفهرسة.
NOISE_HEADING_RE = re.compile(r"كيف\s*ت[تق][قت]*ن|^\s*\d+\s*$|^\s*[\d\u0660-\u0669]+\s*\|")

# أسطر هي أمثلة/شرح لا عناوين، تُستبعد من مسوّدة العناوين.
EXAMPLE_PREFIXES = (
    "مثال", "مثل", "التوضيح", "الحالة", "الخلاصة", "ملاحظة", "تنبيه",
    "قال", "قوله", "أي", "إعراب", "الاعراب", "تدريب", "سؤال", "جواب",
)


def normalize(text: str) -> str:
    """يُرجع نصًّا مُطبَّعًا صالحًا للمطابقة المعجمية."""
    text = TASHKEEL_RE.sub("", text)
    text = text.translate(LETTER_MAP).translate(DIGIT_MAP)
    text = NON_WORD_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_page(raw: str) -> tuple[str, list[tuple[int, str]]]:
    """يُطبّع صفحة كاملة سطرًا سطرًا ويستخرج مرشّحات العناوين.

    يُرجع (النص المطبَّع، قائمة (المستوى، العنوان) من النص الأصلي).
    المستوى 1/2/3 لعناوين Markdown، و0 للسطور الغامقة القصيرة.
    """
    norm_lines: list[str] = []
    headings: list[tuple[int, str]] = []

    for i, line in enumerate(raw.splitlines()):
        stripped = line.strip()

        # حذف ترويسة الصفحة من أول سطر فقط.
        if i == 0 and RUNNING_HEADER_RE.match(stripped):
            stripped = RUNNING_HEADER_RE.sub("", stripped)

        md = MD_HEADING_RE.match(stripped)
        if md:
            title = md.group(2).strip()
            # استبعاد ترويسات الصفحات الملتقطة كعناوين (مثل «كَيْفَ تُتْقِنُ البَلَاغَةَ؟ | 26»).
            if not NOISE_HEADING_RE.search(normalize(title)):
                headings.append((len(md.group(1)), title))
        else:
            m = BOLD_LINE_RE.match(stripped)
            if m:
                candidate = m.group(1).strip()
                plain = normalize(candidate)
                if (
                    0 < len(candidate) <= 70
                    and len(plain.split()) <= 7        # عنوان لا جملة
                    and not any(plain.startswith(p) for p in EXAMPLE_PREFIXES)
                ):
                    headings.append((0, candidate))

        norm = normalize(stripped)
        if norm:
            norm_lines.append(norm)

    return "\n".join(norm_lines), headings


# ---------------------------------------------------------------- الفهرسة

def page_number(path: Path) -> int | None:
    m = re.fullmatch(r"page_(\d+)\.md", path.name)
    return int(m.group(1)) if m else None


def build_book(book_dir: Path, dry_run: bool = False) -> dict:
    """يبني فهرس كتاب واحد ويُرجع تقريره.

    dry_run=True: يحسب كل شيء ويُرجع التقرير بلا كتابة أي ملف في index/.
    """
    pages = [(page_number(p), p) for p in book_dir.glob("page_*.md")]
    pages = sorted((n, p) for n, p in pages if n is not None)
    if not pages:
        return {"book": book_dir.name, "status": "لا توجد صفحات"}

    norm_dir = INDEX_DIR / book_dir.name / "norm"
    if not dry_run:
        norm_dir.mkdir(parents=True, exist_ok=True)

    headings_rows: list[str] = []
    total_chars = 0
    empty_pages: list[int] = []

    for n, path in pages:
        raw = path.read_text(encoding="utf-8", errors="replace")
        norm, headings = normalize_page(raw)
        if not dry_run:
            (norm_dir / f"page_{n:03d}.txt").write_text(norm + "\n", encoding="utf-8")
        total_chars += len(norm)
        if len(norm) < 40:
            empty_pages.append(n)
        for level, h in headings:
            headings_rows.append(f"{n}\t{level}\t{h}")

    existing = {n for n, _ in pages}
    highest = max(existing)
    missing = [n for n in range(1, highest + 1) if n not in existing]

    manifest = {
        "book": book_dir.name,
        "source": str(book_dir.relative_to(WORKSPACE)).replace("\\", "/"),
        "pages_indexed": len(pages),
        "highest_page": highest,
        "missing_pages": missing,
        "sparse_pages": empty_pages,
        "normalized_chars": total_chars,
        # الإزاحة المعلنة في catalog.yaml: عدد الصفحة المطبوع = رقم الملف + الإزاحة
        "printed_page_offset": printed_page_offset(book_dir.name),
        "normalized_dir": str((INDEX_DIR / book_dir.name / "norm").relative_to(WORKSPACE)).replace("\\", "/"),
    }
    if not dry_run:
        (INDEX_DIR / book_dir.name / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (INDEX_DIR / book_dir.name / "headings_draft.tsv").write_text(
            "\n".join(headings_rows) + "\n", encoding="utf-8"
        )
    return manifest


def run_guard() -> int:
    """يشغّل حارس مساحة العمل (scripts/validate_all.py) ويعيد رمز خروجه."""
    script = WORKSPACE / "scripts" / "validate_all.py"
    if not script.exists():
        return 0
    sys.stdout.flush()  # حتى تظهر مخرجات الحارس بترتيبها لا قبل مخرجات الأب
    return subprocess.run([sys.executable, str(script), "--quiet"], cwd=str(WORKSPACE)).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="بناء فهرس معجمي لكتب output/")
    parser.add_argument("--book", help="اسم كتاب واحد فقط (افتراضي: كل الكتب)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="فحص فقط: يحسب الصفحات والفجوات بلا كتابة أي ملف في index/",
    )
    args = parser.parse_args()

    if not OUTPUT_DIR.exists():
        print(f"[!] لا يوجد مجلد: {OUTPUT_DIR}")
        return 1

    books = [OUTPUT_DIR / args.book] if args.book else sorted(
        d for d in OUTPUT_DIR.iterdir() if d.is_dir()
    )

    print("=" * 60)
    if args.dry_run:
        print("[i] وضع الفحص (--dry-run): لن يُكتب أي ملف في index/.")
    for book_dir in books:
        if not book_dir.exists():
            print(f"[!] كتاب غير موجود: {book_dir.name}")
            continue
        m = build_book(book_dir, dry_run=args.dry_run)
        print(f"[✓] {m['book']}: {m.get('pages_indexed', 0)} صفحة | "
              f"{m.get('normalized_chars', 0):,} حرف | "
              f"فجوات: {len(m.get('missing_pages', []))}")
        if m.get("missing_pages"):
            mp = m["missing_pages"]
            shown = ", ".join(str(x) for x in mp[:12]) + (" ..." if len(mp) > 12 else "")
            print(f"    صفحات ناقصة: {shown}")
    print("=" * 60)
    if args.dry_run:
        print("[i] انتهى الفحص بلا كتابة. للحفظ: أعد التشغيل بلا --dry-run.")
        return 0
    print(f"[i] المخرجات في: {INDEX_DIR.relative_to(WORKSPACE)}/")
    return run_guard()


if __name__ == "__main__":
    sys.exit(main())
