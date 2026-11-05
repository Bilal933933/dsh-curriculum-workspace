# -*- coding: utf-8 -*-
"""
plans_year_audit.py — تدقيق سنة التوزيعات من النص المحوَّل.

لماذا
-----
التوزيعات المنقولة إلى `plans/text` تجميع ارتجالي من أعوام مختلفة، وبعضها قد
يكون قديمًا (2024/2025) فيُضلّل المعلم. نحتاج دليلًا نصيًّا على السنة قبل
الاعتماد، ومصدره الملفات الأصلية (`curriculum_raw/<name>_images`) لا ذاكرتنا.

ما يقرأه
--------
`plans/text/<plan>/page_*.md` فقط (قراءة).

ما يكتبه
--------
لا شيء — يطبع تقريرًا على الشاشة (و`--json` للمسار المعطى).

الاستخدام
---------
    python scripts/audit/plans_year_audit.py
    python scripts/audit/plans_year_audit.py --only-distributions
    python scripts/audit/plans_year_audit.py --json meta/plans_year_audit.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLANS = ROOT / "plans" / "text"

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

# أرقام عربية-هندية ← لاتينية (تظهر في كثير من الجداول)
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

YEAR = re.compile(r"(?<!\d)(20[1-3]\d)(?!\d)")
PAIR = re.compile(r"20[1-3]\d\s*[/\-–]\s*20[1-3]\d")
SEASON = re.compile(r"الفصل\s+الدراسي\s+(الأول|الثاني|الدراسي)")

# عنوان التوزيع يحدد المادة والصف
SUBJECTS = [
    "اللغة العربية", "اللغة الإنجليزية", "اللغة الفرنسية", "الرياضيات", "العلوم",
    "الدراسات الاجتماعية", "التربية الدينية", "تكنولوجيا المعلومات", "الحاسب",
    "البرمجة", "مهارات الصناعة", "التربية الموسيقية", "التاريخ", "الجغرافيا",
    "الفيزياء", "الكيمياء", "الأحياء",
]


def norm_year(tokens: list[str]) -> list[str]:
    return sorted({t for t in tokens if 2015 <= int(t) <= 2035})


def scan_plan(d: Path) -> dict:
    files = sorted(d.glob("page_*.md"))
    years: dict[str, str] = {}
    pairs: set[str] = set()
    seasons: set[str] = set()
    for f in files:
        t = f.read_text(encoding="utf-8", errors="ignore").translate(AR_DIGITS)
        for m in YEAR.finditer(t):
            years.setdefault(m.group(1), f.name)
        for m in PAIR.finditer(t):
            pairs.add(re.sub(r"\s+", "", m.group(0)))
        for m in SEASON.finditer(t):
            seasons.add(m.group(1))
    return {
        "name": d.name,
        "pages": len(files),
        "years": {y: years[y] for y in sorted(years)},
        "pairs": sorted(pairs),
        "seasons": sorted(seasons),
    }


def subject_of(name: str) -> str:
    flat = name.replace("_", " ")
    for s in SUBJECTS:
        if s in flat:
            return s
    return "غير محدد"


def main() -> int:
    ap = argparse.ArgumentParser(description="تدقيق سنوات التوزيعات")
    ap.add_argument("--only-distributions", action="store_true",
                    help="التوزيعات فقط (الاسم يبدأ بـ«توزيع»)")
    ap.add_argument("--json", help="كتابة التقرير إلى هذا المسار")
    args = ap.parse_args()

    dirs = sorted(p for p in PLANS.iterdir() if p.is_dir())
    rows = []
    for d in dirs:
        if args.only_distributions and not d.name.startswith("توزيع"):
            continue
        r = scan_plan(d)
        r["subject"] = subject_of(r["name"])
        rows.append(r)

    print(f"عدد الخطط المفحوصة: {len(rows)}\n")
    for r in rows:
        ys = "، ".join(r["years"]) or "—"
        pr = " / ".join(r["pairs"]) or "—"
        flag = ""
        if "2026" not in ys and "2027" not in ys:
            flag = "  ← لا ذكر لسنة 2026/2027"
        print(f"{r['name'][:56]:<58} {r['pages']:>2}ص | سنوات: {ys:<12} | زوج: {pr}{flag}")

    if args.json:
        out = Path(args.json)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[*] التقرير: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
