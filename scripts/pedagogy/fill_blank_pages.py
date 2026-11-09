#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fill_blank_pages.py — إغلاق الصفحات البيضاء التي لا ينتج عنها نص.
================================================================
المشكلة:
    كتب PDF فيها صفحات بيضاء (فواصل فصول) أو صفحات برقم صفحة فقط.
    محوّل الرؤية يعتبرها «فشلًا: نص قصير/فارغ»، فيبقى الكتاب ناقصًا
    في عدّ الصفحات ويرفضه الحارس.

الحل:
    لكل صفحة ناقصة: يُفحص أصلها في PDF.
      • نصها < 10 حروف وبلا صور  ⇒ صفحة بيضاء فعلًا: تُكتب صفحة توضيحية
        `<!-- صفحة بيضاء في المصدر -->` (لا نص مُختلق).
      • لها نص أو صورة          ⇒ تُترك ويُبلَّغ عنها لمعالجتها بصريًا.

المخرجات:
    output/<book>/page_XXX.md   (للصفحات البيضاء فقط)
    تقرير على stdout

الاستخدام:
    python scripts/pedagogy/fill_blank_pages.py --pdf curriculum_raw/X.pdf --book X
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pymupdf

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

ROOT = Path(__file__).resolve().parents[2]
LETTER = re.compile(r"[\u0621-\u064a]")
BLANK_MARK = "<!-- صفحة بيضاء في المصدر: لا نص ولا صورة -->\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="كتابة صفحات بيضاء وإبلاغ عن غيرها")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--book", required=True)
    args = ap.parse_args()

    pdf = Path(args.pdf)
    if not pdf.is_absolute():
        pdf = ROOT / pdf
    book_dir = ROOT / "output" / args.book
    if not book_dir.is_dir():
        print(f"[!] لا مجلد مخرجات: {book_dir}")
        return 2

    doc = pymupdf.open(str(pdf))
    total = doc.page_count
    have = {int(p.stem[5:8]) for p in book_dir.glob("page_*.md") if p.stat().st_size > 100}
    missing = [p for p in range(1, total + 1) if p not in have]

    filled, left = [], []
    for p in missing:
        page = doc[p - 1]
        text = page.get_text().strip()
        imgs = page.get_images(full=True)
        if len(LETTER.findall(text)) < 10 and not imgs and len(text) < 60:
            (book_dir / f"page_{p:03d}.md").write_text(BLANK_MARK, encoding="utf-8")
            filled.append(p)
        else:
            left.append((p, len(text), len(imgs)))
    doc.close()

    print(f"[*] {args.book}: ناقص {len(missing)} | بيضاء كُتبت {len(filled)} | تحتاج معالجة {len(left)}")
    if filled:
        print("    بيضاء: " + ", ".join(map(str, filled)))
    for p, lt, li in left:
        print(f"    [!] ص {p}: نص {lt} حرفًا، صور {li} — تحتاج تحويلًا بصريًا")
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main())
