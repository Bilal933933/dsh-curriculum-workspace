#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
استخراج الطبقة النصية من PDF (Text-Layer Extractor) — بلا أي استدعاء نموذج
==========================================================================
الغرض:
    تحويل الكتب الرقمية التي تحتوي طبقة نصية حقيقية إلى Markdown مباشرة،
    دون صور ودون توكنز. وهو المسار الأول والأرخص في مهارة `pdf-text-parser`.

    الكتاب الممسوح (بلا طبقة نصية) لا يصلح لهذا المسار؛ يُكتشف ذلك آليًا
    وتُكتب قائمة الصفحات التي تحتاج OCR البصري.

المميزات:
    - استخراج نصي أصلي (بلا نموذج) = صفر توكنز للصفحات النصية.
    - استكشاف آلي: لكل صفحة يُصنَّف الحال: نصّية | قصيرة | بلا نص.
    - تطبيع عربي: تحويل أشكال العرض (Presentation Forms) إلى حروف أساس،
      إزالة محارف التحكم والعرض الصفري، ضبط المسافات والأسطر.
    - استخراج الجداول (إن وجدت) إلى جداول Markdown عبر find_tables().
    - --ocr-missing: يحوّل الصفحات غير النصية فقط إلى صور ثم يستدعي
      run_vision_batch.py عليها (تحويل هجين بأقل توكنز ممكن).

الملفات التي يقرأها:
    - ملف PDF المحدد في --pdf.

الملفات التي يكتبها:
    - output/<book>/page_XXX.md                       (الصفحات النصية)
    - logs/chapters/<book>/text_layer_report.md       (تقرير التصنيف والأعلام)
    - logs/chapters/<book>/ocr_needed.txt             (أرقام الصفحات التي تحتاج OCR)
    - curriculum_raw/<book>_images/page_XXX.png       (فقط مع --ocr-missing)

الاستخدام:
    python scripts/pdf_text_extract.py --pdf curriculum_raw/<book>.pdf --book <book>
    python scripts/pdf_text_extract.py --pdf curriculum_raw/<book>.pdf --book <book> --ocr-missing
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent.parent

# ------------------------------------------------------------------ أنماط عربية
_CTRL = re.compile("[\u200b\u200c\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_PRESENTATION = re.compile("[\ufb50-\ufdff\ufe70-\ufeff]")
_LETTER = re.compile("[\u0621-\u064a]")
_DIACRITIC = re.compile("[\u064b-\u0652\u0670]")
_WS_RUN = re.compile(r"[ \t]{2,}")
_NL_RUN = re.compile(r"\n{3,}")


def normalize(text: str) -> tuple[str, int]:
    """تطبيع النص العربي. يعيد (النص، عدد محارف العرض التي حُوِّلت)."""
    presentation = len(_PRESENTATION.findall(text))
    if presentation:
        text = unicodedata.normalize("NFKC", text)
    text = _CTRL.sub("", text).replace("\u00a0", " ")
    text = "\n".join(_WS_RUN.sub(" ", ln).strip() for ln in text.splitlines())
    text = _NL_RUN.sub("\n\n", text).strip()
    return text, presentation


_MIRROR = str.maketrans({"(": ")", ")": "(", "[": "]", "]": "[", "{": "}",
                         "}": "{", "«": "»", "»": "«", "<": ">", ">": "<"})
# وحدة عربية = حرف + ما يتبعه من حركات (كي لا تنفصل الحركة عن حرفها عند العكس)
_CLUSTER = re.compile(r"[^\u064b-\u0652\u0670\u0653-\u065f\u06d6-\u06ed]"
                      r"[\u064b-\u0652\u0670\u0653-\u065f\u06d6-\u06ed]*", re.S)
_KEEP_RUN = re.compile(r"[0-9]+(?:[/.:,\-][0-9]+)*|[A-Za-z]+")
_SENT_PUNCT = ".،؛؟!:"


def reverse_clusters(text: str) -> str:
    """يعكس ترتيب النص مع الحفاظ على وحدة الحرف وحركته."""
    return "".join(reversed(_CLUSTER.findall(text)))


def fix_visual_line(line: str) -> str:
    """يصلح سطرًا مُستخرجًا بترتيب بصري (مقلوب) إلى ترتيب منطقي."""
    rev = reverse_clusters(line).translate(_MIRROR)
    return _KEEP_RUN.sub(lambda m: m.group(0)[::-1], rev)


def looks_visual(text: str) -> bool:
    """يكشف هل النص مُستخرج بالترتيب البصري (سطر يبدأ بعلامة نهاية الجملة)."""
    lines = [ln.strip() for ln in text.splitlines() if len(_LETTER.findall(ln)) >= 8]
    if len(lines) < 3:
        return False
    starts = sum(1 for ln in lines if ln[0] in _SENT_PUNCT)
    ends = sum(1 for ln in lines if ln[-1] in _SENT_PUNCT)
    return starts >= 2 and starts > ends * 2


_SPACED_MARK = re.compile(r"\s[\u064b-\u0652\u0670]")
_TAB = re.compile("\t")
_TOKEN = re.compile(r"\S+")


def text_defects(text: str) -> list[str]:
    """عيوب طبقة نصية تجعلها أسوأ من OCR (كلمات مقطوعة/حركات منفصلة/أعمدة).

    كثرة هذه العيوب تعني أن الـ PDF خرج من محوّل قديم (Ghostscript) فبعثر
    المقاطع؛ وحينها التحويل البصري أدق من النص الأصلي.
    """
    defects = []
    marks = len(_SPACED_MARK.findall(text))
    if marks >= 3:
        defects.append(f"حركات منفصلة×{marks}")
    tabs = len(_TAB.findall(text))
    if tabs >= 2:
        defects.append(f"جدولة×{tabs}")
    tokens = _TOKEN.findall(text)
    if tokens:
        tiny = sum(1 for t in tokens if len(_LETTER.findall(t)) == 1
                   and t not in {"و", "ف", "ب", "ل", "ك", "أ", "ا"})
        if tiny / len(tokens) > 0.15:
            defects.append(f"حروف مفردة {tiny}/{len(tokens)}")
    if text and text.count(".") / len(text) > 0.15:
        defects.append("نقاط قائدة")
    return defects


def page_flags(text: str, presentation_fixed: int) -> list[str]:
    """علامات شبهة نصية (بلا نموذج) تُستخدم لتقرير الطبقة النصية."""
    flags = []
    letters = len(_LETTER.findall(text))
    diacritics = len(_DIACRITIC.findall(text))
    if presentation_fixed:
        flags.append("أشكال عرض")
    if letters > 80 and diacritics < letters * 0.02:
        flags.append("تشكيل ناقص")
    if re.search(r"[\u0600-\u06ff]\S{40,}", text):
        flags.append("بلا مسافات")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 8 and len(set(lines)) < len(lines) * 0.6:
        flags.append("أسطر مكررة")
    return flags


def page_to_markdown(page) -> str:
    """نص الصفحة كـ Markdown، مع تحويل أي جدول مُكتشف إلى جدول Markdown."""
    tables = []
    try:
        tables = page.find_tables().tables
    except Exception:
        tables = []

    parts = []
    if tables:
        for table in tables:
            rows = table.extract()
            rows = [[(c or "").replace("\n", " ").strip() for c in row] for row in rows if row]
            if len(rows) < 2:
                continue
            width = max(len(r) for r in rows)
            rows = [r + [""] * (width - len(r)) for r in rows]
            md = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
            md += ["| " + " | ".join(r) + " |" for r in rows[1:]]
            parts.append("\n".join(md))
        # نص الصفحة كاملًا بعد الجداول (لا يُستبعد شيء)
    body = page.get_text("text")
    if body.strip():
        parts.append(body)
    return "\n\n".join(parts)


def render_pages(doc, book: str, pages: list[int], dpi: int = 260) -> Path:
    """يرسم صفحات محددة فقط إلى PNG (توفير مساحة ووقت)."""
    img_dir = ROOT / "curriculum_raw" / f"{book}_images"
    img_dir.mkdir(parents=True, exist_ok=True)
    zoom = dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    for p in pages:
        dest = img_dir / f"page_{p:03d}.png"
        if dest.exists() and dest.stat().st_size > 10_000:
            continue
        doc[p - 1].get_pixmap(matrix=matrix, alpha=False).save(str(dest))
    return img_dir


def runs(pages: list[int]) -> list[tuple[int, int]]:
    """يجمع أرقام الصفحات المتجاورة في مدىات (start, end)."""
    out = []
    for p in sorted(pages):
        if out and p == out[-1][1] + 1:
            out[-1] = (out[-1][0], p)
        else:
            out.append((p, p))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="استخراج الطبقة النصية من PDF إلى Markdown")
    ap.add_argument("--pdf", required=True, help="مسار ملف PDF")
    ap.add_argument("--book", required=True, help="اسم الكتاب (مجلد المخرجات والسجلات)")
    ap.add_argument("--out", default=None, help="مجلد المخرجات (افتراضي: output/<book>)")
    ap.add_argument("--start", type=int, default=1, help="أول صفحة (1-based)")
    ap.add_argument("--end", type=int, default=0, help="آخر صفحة (0 = حتى النهاية)")
    ap.add_argument("--min-chars", type=int, default=40,
                    help="أقل عدد حروف لاعتبار الصفحة نصية (افتراضي 40)")
    ap.add_argument("--force", action="store_true", help="إعادة الكتابة حتى لو الملف موجود")
    ap.add_argument("--ocr-missing", action="store_true",
                    help="رسم الصفحات غير النصية واستدعاء run_vision_batch عليها")
    ap.add_argument("--workers", type=int, default=3, help="توازي التحويل البصري (مع --ocr-missing)")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    if not pdf.exists():
        print(f"خطأ: لا يوجد ملف PDF: {pdf}")
        return 2

    out_dir = Path(args.out) if args.out else ROOT / "output" / args.book
    log_dir = ROOT / "logs" / "chapters" / args.book
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open(pdf)
    total = doc.page_count
    end = min(args.end or total, total)
    if not (1 <= args.start <= end):
        print(f"خطأ: مدى غير صالح {args.start}–{end} (الكتاب {total} صفحة)")
        return 2

    written = skipped = short = empty = 0
    ocr_needed: list[int] = []
    report_rows: list[str] = []

    for p in range(args.start, end + 1):
        dest = out_dir / f"page_{p:03d}.md"

        # مسار سريع عند الاستئناف: صفحة محوَّلة مسبقًا تُتخطى بلا تحليل ولا رسم.
        # (تحليل كل صفحة عبر find_tables مكلف، وكان يضيّع دقائق في كل إعادة تشغيل.)
        if dest.exists() and dest.stat().st_size > 100 and not args.force:
            skipped += 1
            report_rows.append(f"| {p} | — | — | موجودة مسبقًا (تخطي) |")
            continue

        page = doc[p - 1]
        raw = page_to_markdown(page)
        text, fixed = normalize(raw)

        # إصلاح الترتيب البصري (بعض برامج PDF تُخرج النص مقلوبًا)
        visual = looks_visual(text)
        if visual:
            text = "\n".join(fix_visual_line(ln) for ln in text.splitlines()).strip()

        if len(_LETTER.findall(text)) < args.min_chars:
            empty += 1 if not text.strip() else 0
            short += 0 if not text.strip() else 1
            ocr_needed.append(p)
            report_rows.append(f"| {p} | {len(text)} | — | بلا طبقة نصية → OCR |")
            continue

        flags = page_flags(text, fixed)
        if visual:
            flags.insert(0, "عُكس ترتيبه")

        # عيوب الطبقة النصية: إن كانت فادحة فالتحويل البصري أدق ⇒ OCR
        defects = text_defects(text)
        strong = any(d.startswith(("حركات منفصلة", "جدولة", "نقاط قائدة")) for d in defects)
        if strong:
            ocr_needed.append(p)
            report_rows.append(
                f"| {p} | {len(text)} | {fixed} | طبقة نصية معطوبة ({', '.join(defects)}) → OCR |")
            continue

        report_rows.append(f"| {p} | {len(text)} | {fixed} | {', '.join(flags + defects) or 'سليم'} |")

        if dest.exists() and dest.stat().st_size > 100 and not args.force:
            skipped += 1
            continue
        dest.write_text(text.rstrip() + "\n", encoding="utf-8")
        written += 1

    # ---------------------------------------------------------------- التقرير
    report = log_dir / "text_layer_report.md"
    header = (
        f"# تقرير الطبقة النصية — {args.book}\n\n"
        f"- **المدى:** {args.start}–{end} من {total}\n"
        f"- **مكتوبة:** {written} | **موجودة مسبقًا:** {skipped}\n"
        f"- **تحتاج OCR:** {len(ocr_needed)} صفحة\n"
        f"- **تاريخ:** تم\n\n"
        "| صفحة | حروف | أشكال عرض | أعلام |\n|---|---|---|---|\n"
    )
    report.write_text(header + "\n".join(report_rows) + "\n", encoding="utf-8")
    (log_dir / "ocr_needed.txt").write_text(
        "\n".join(str(p) for p in sorted(ocr_needed)) + ("\n" if ocr_needed else ""),
        encoding="utf-8")

    print(f"[*] {pdf.name} | {total} صفحة | المدى {args.start}–{end}")
    print(f"[✓] نصّية مكتوبة {written} | موجودة {skipped} | تحتاج OCR {len(ocr_needed)}")
    if ocr_needed:
        spans = [f"{s}" if s == e else f"{s}–{e}" for s, e in runs(ocr_needed)]
        print(f"[!] صفحات OCR: {', '.join(spans) if len(ocr_needed) <= 60 else str(len(ocr_needed)) + ' صفحة'}")
    print(f"[*] التقرير: {report.relative_to(ROOT)}")

    # ------------------------------------------------- التحويل البصري للناقص
    if args.ocr_missing and ocr_needed:
        render_pages(doc, args.book, ocr_needed)
        print(f"[*] رُسمت صور {len(ocr_needed)} صفحة فقط (لا الكتاب كله)")
        code = 0
        for s, e in runs(ocr_needed):
            print(f"[*] OCR: {s}–{e}")
            import subprocess
            code = subprocess.run(
                [sys.executable, "scripts/convert/run_vision_batch.py",
                 "--book", args.book, "--start", str(s), "--end", str(e),
                 "--workers", str(args.workers), "--timeout", "90"],
                cwd=str(ROOT)).returncode
            if code == 3:
                print("[⛔] نفدت الحصة — أوقف التحويل البصري")
                break
        return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
