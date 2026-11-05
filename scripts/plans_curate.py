#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plans_curate.py — فصل التوزيعات الحقيقية عن صفحات الكتب المسحوبة خطأً.

الخلفية: مجلد «توزيع-المناهج-2026-2027» المستخرج من كتب الأضواء يحتوي على
صفحات كتب مدرسية عشوائية، لا توزيعات. الفحص النصي يميّز التوزيع الحقيقي
بوجود مؤشرات جدول أسبوعي/فصلي («الأسبوع»، «الحصة»، «الفصل الدراسي») وكلمة
«توزيع/خطة» بكثرة.

المخرج: حقل `role` في meta/plans.yaml:
    plan      = توزيع منهج فعلي (كل الوحدات الرسمية + المستخرجة الحقيقية)
    not_plan  = صفحات كتاب/فهرس سُحبت خطأً — لا تُستشهد كتوزيع

الاستخدام (من مجلد workspace):
    python scripts/plans_curate.py            # تطبيق
    python scripts/plans_curate.py --dry-run  # عرض فقط
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "meta" / "plans.yaml"
OUT = ROOT / "output"

MARKERS = re.compile("الأسبوع|اسبوع|الحصة|الشهر|الفصل الدراسي")
PLAN_WORDS = ("توزيع", "خطة")
MIN_MARKERS = 2  # لا بد من مؤشرات جدول زمني فعلية


def stats(text_dir: str) -> tuple[int, int]:
    """(عدد كلمة «توزيع»، عدد مؤشرات الجدول الزمني) في أول 4 صفحات."""
    pages = sorted((OUT / text_dir).glob("page_*.md"))
    words = marks = 0
    for f in pages[:4]:
        t = f.read_text(encoding="utf-8", errors="replace")
        marks += len(MARKERS.findall(t))
        words += sum(t.count(w) for w in PLAN_WORDS)
    return words, marks


def score(text_dir: str) -> int:
    """درجة مساعدة للعرض فقط."""
    words, marks = stats(text_dir)
    return 5 * words + marks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = yaml.safe_load(REG.read_text(encoding="utf-8")) or {}
    units = data.get("units", [])

    changed = []
    for u in units:
        before = u.get("role")
        if u["authority"] == "official":
            role = "plan"
        else:
            words, marks = stats(u["text_dir"])
            role = "plan" if (words >= 1 and marks >= MIN_MARKERS) else "not_plan"
            u["_score"] = f"{words}w/{marks}m"
        if before != role:
            u["role"] = role
            changed.append((u["id"], before, role, u.get("_score")))

    for uid, before, role, s in changed:
        print(f"{uid:34} {str(before):9} ← {role:9} {'' if s is None else f'({s})'}")
    for u in units:
        u.pop("_score", None)

    plans = sum(1 for u in units if u.get("role") == "plan")
    non = sum(1 for u in units if u.get("role") == "not_plan")
    print(f"\nخطة: {plans} | ليست خطة: {non} | تغييرات: {len(changed)}")

    if args.dry_run:
        print("[i] تجربة — لم يُكتب شيء.")
        return 0
    if changed:
        REG.write_text(
            yaml.safe_dump({"version": 1, "units": units}, allow_unicode=True,
                           sort_keys=False, width=200),
            encoding="utf-8")
        print(f"[✓] حُدّث {REG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
