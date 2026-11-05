#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plans_official_ingest.py — استيعاب توزيعات المناهج الرسمية من مجلد التنزيلات.

لماذا
-----
`plans/text` القديمة كانت تفريغًا ارتجاليًا مختلطًا (توزيعات + كتب + امتحانات).
هذا السكربت يبني طبقة نظيفة من المصدر الرسمي: مجلد مرتّب `مرحلة/<صف>/<مادة>.pdf`.

ما يفعله
--------
1. ينسخ كل PDF إلى `plans_src/official/<مرحلة>/<صف>/<مادة>.pdf` (نسخ لا نقل).
2. يكتب سجلًا `meta/plans_official.yaml` لكل وحدة: id، العنوان، المرحلة، الصف، المادة،
   المسار، text_dir، عدد الصفحات (من pymupdf)، والحالة.

الاستخدام
---------
    python scripts/convert/plans_official_ingest.py --dry-run
    python scripts/convert/plans_official_ingest.py --apply
    python scripts/convert/plans_official_ingest.py --apply --src "<مسار آخر>"
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

import pymupdf
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEST_ROOT = ROOT / "plans_src" / "official"
REGISTRY = ROOT / "meta" / "plans_official.yaml"
DEFAULT_SRC = Path(os.path.expanduser("~")) / "Downloads" / "توزيع-المناهج-2026-2027"

STAGES = ("رياض الأطفال", "الابتدائية", "الإعدادية", "الثانوي العام")

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def safe(name: str) -> str:
    """يجعل الاسم صالحًا لمجلد: بلا مسافات ولا محارف ممنوعة."""
    name = name.strip().replace(" ", "_")
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def collect(src: Path) -> list[dict]:
    units = []
    for stage in STAGES:
        sdir = src / stage
        if not sdir.is_dir():
            continue
        for grade_dir in sorted(p for p in sdir.iterdir() if p.is_dir()):
            for pdf in sorted(grade_dir.glob("*.pdf")):
                subject = pdf.stem
                text_dir = f"توزيع_رسمي_{safe(subject)}_{safe(grade_dir.name)}"
                if stage == "رياض الأطفال":
                    text_dir += "_رياض_الأطفال"
                rel = Path("plans_src") / "official" / stage / grade_dir.name / pdf.name
                try:
                    pages = pymupdf.open(str(pdf)).page_count
                except Exception as exc:  # noqa: BLE001
                    print(f"[!] تعذّر فتح {pdf.name}: {exc}")
                    pages = 0
                units.append({
                    "id": "",
                    "title": f"توزيع منهج {subject} — {grade_dir.name}",
                    "authority": "official",
                    "kind": "pdf",
                    "source": rel.as_posix(),
                    "text_dir": text_dir,
                    "pages": pages,
                    "status": "pending",
                    "pages_converted": 0,
                    "stage": stage,
                    "grade": grade_dir.name,
                    "subject": subject,
                    "role": "plan",
                    "note": None,
                })
    # ترقيم ثابت حسب ترتيب المراحل ثم الصفوف ثم المواد
    for i, u in enumerate(units, start=1):
        u["id"] = f"plan_of_{i:03d}"
    return units


def main() -> int:
    ap = argparse.ArgumentParser(description="استيعاب توزيعات المناهج الرسمية")
    ap.add_argument("--src", default=str(DEFAULT_SRC), help="مجلد المصدر")
    ap.add_argument("--apply", action="store_true", help="نسخ فعلي وكتابة السجل")
    ap.add_argument("--dry-run", action="store_true", help="عرض فقط (الافتراضي)")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.is_dir():
        print(f"[!] المجلد غير موجود: {src}")
        return 2

    units = collect(src)
    total_pages = sum(u["pages"] for u in units)
    print(f"[*] وحدات: {len(units)} | صفحات: {total_pages}")
    for stage in STAGES:
        group = [u for u in units if u["stage"] == stage]
        if group:
            print(f"    {stage}: {len(group)} مادة")

    if not args.apply:
        print("\n[dry-run] لم يُنسخ شيء. أمثلة:")
        for u in units[:5]:
            print(f"    {u['id']} | {u['text_dir']} | {u['pages']} ص | {u['source']}")
        return 0

    copied = skipped = 0
    for u in units:
        dst = ROOT / u["source"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and dst.stat().st_size > 1024:
            skipped += 1
        else:
            shutil.copy2(src / u["stage"] / u["grade"] / f"{u['subject']}.pdf", dst)
            copied += 1

    REGISTRY.write_text(
        yaml.safe_dump({"version": 1, "units": units}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"[+] نُسخ {copied} | موجود مسبقًا {skipped} | السجل: {REGISTRY.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
