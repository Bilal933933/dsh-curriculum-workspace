#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
queue_status.py — لوحة حالة التحويل (قراءة فقط، بلا أي استدعاء نموذج).
=======================================================================
تعرض لكل كتاب: عدد الصفحات المحوَّلة من 총 المصدر، والفجوات، وعدد الصفحات
المكتوبة في آخر N دقيقة (لقياس المعدل الفعلي أثناء العمل).

الملفات التي يقرؤها:
    curriculum_raw/<book>.pdf        (عدد الصفحات)
    output/<book>/page_XXX.md        (المحوَّل)
    meta/catalog.yaml                (هل سُجّل الكتاب؟)

الاستخدام:
    python scripts/queue_status.py            # آخر 5 دقائق
    python scripts/queue_status.py --minutes 15
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "output"
RAW = ROOT / "curriculum_raw"
CATALOG = ROOT / "meta" / "catalog.yaml"

# مجلد المخرجات ← معرّف الفهرس
BOOKS = {
    "اللغة_العربية_الصف_الأول_ت1": "arabic_p1_t1",
    "اللغة_العربية_الصف_الثاني_ت1": "arabic_p2_t1",
    "اللغة_العربية_الصف_الثالث_ت1": "arabic_p3_t1",
    "اللغة_العربية_الصف_الرابع_ت1": "arabic_p4_t1",
    "اللغة_العربية_الصف_الخامس_ت1": "arabic_p5_t1",
    "اللغة_العربية_الصف_السادس_ت1": "arabic_p6_t1",
    "اللغة_العربية_الصف_الأول_الإعدادي_ت1": "arabic_prep1_t1",
    "اللغة_العربية_الصف_الثاني_الإعدادي_ت1": "arabic_prep2_t1",
    "اللغة_العربية_الصف_الثالث_الإعدادي_ت1": "arabic_prep3_t1",
    "الإعراب_الميسر": "erab_muyassar",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=5, help="نافذة قياس المعدل")
    args = ap.parse_args()

    for s in (sys.stdout,):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    catalog = CATALOG.read_text(encoding="utf-8") if CATALOG.exists() else ""
    window = args.minutes * 60
    now = time.time()

    rows, total_all, done_all, recent_all = [], 0, 0, 0
    for book, bid in BOOKS.items():
        pdf = RAW / f"{book}.pdf"
        total = pymupdf.open(pdf).page_count if pdf.exists() else 0
        d = OUT / book
        files = sorted(f for f in d.glob("page_*.md")) if d.is_dir() else []
        done = len(files)
        recent = sum(1 for f in files if now - f.stat().st_mtime < window)
        gaps = total - done
        registered = f"- id: {bid}" in catalog
        rows.append((book, done, total, gaps, recent, registered))
        total_all += total
        done_all += done
        recent_all += recent

    print(f"{'الكتاب':44s} {'محوَّل':>9s} {'فجوات':>7s} {f'آخر{args.minutes}د':>8s}  مسجَّل")
    for book, done, total, gaps, recent, reg in rows:
        print(f"{book:44s} {done:4d}/{total:<4d} {gaps:7d} {recent:8d}  {'✓' if reg else '—'}")
    print("-" * 84)
    print(f"الإجمالي: {done_all}/{total_all} صفحة | متبقٍ {total_all - done_all} | "
          f"معدل {recent_all / max(args.minutes, 1):.1f} صفحة/دقيقة "
          f"(≈ {int((total_all - done_all) / max(recent_all / max(args.minutes, 1), 0.1))} دقيقة متوقعة)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
