"""_plans_fidelity.py — فحص مدى مطابقة وحدات التوزيعات لماهيتها (قراءة فقط).

لكل وحدة: هل تحتوي صفحاتها على ما يدل على «توزيع/خريطة منهج» أم أنها صفحات
من كتاب مدرسي (شرح/تدريبات) سُحبت خطأً من كتب الأضواء؟
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "meta" / "plans.yaml"
SIGNALS = ("توزيع", "خريطة المنهج", "خطة توزيع", "الخطة الدراسية",
           "Curriculum Plan", "توزيع المنهج", "مصفوفة")
NOISE = ("تدريبات", "أجب عن", "اختر الإجابة", "كتاب الشرح", "فهرس")


def main() -> int:
    units = (yaml.safe_load(REG.read_text(encoding="utf-8")) or {}).get("units", [])
    print(f"{'المعرّف':32} {'صفحات':>6} {'دلائل':>6}  الحكم")
    counts = {"plan": 0, "unclear": 0, "not_plan": 0}
    for u in units:
        d = ROOT / "output" / u["text_dir"]
        if not d.is_dir():
            continue
        pages = sorted(d.glob("page_*.md"))
        if not pages:
            continue
        hits = 0
        for f in pages:
            t = f.read_text(encoding="utf-8", errors="replace")
            if any(s in t for s in SIGNALS):
                hits += 1
        ratio = hits / len(pages)
        verdict = "خطة" if ratio >= 0.25 else ("غير واضح" if hits else "ليست خطة")
        counts[{"خطة": "plan", "غير واضح": "unclear", "ليست خطة": "not_plan"}[verdict]] += 1
        print(f"{u['id'][:32]:32} {len(pages):6} {hits:6}  {verdict}")
    print(f"\nخطة: {counts['plan']} | غير واضح: {counts['unclear']} | ليست خطة: {counts['not_plan']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
