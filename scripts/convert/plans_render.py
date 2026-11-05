#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plans_render.py — رسم صور صفحات وحدة توزيع إلى curriculum_raw/<text_dir>_images/.

الغرض:
    توحيد مصدرَي التوزيعات (PDF أو مجلد صور) في صورة واحدة: صفحة PNG لكل صفحة،
    حتى يعمل عليها `run_vision_batch.py` كما يعمل على الكتب بلا أي تعديل.

الاستخدام:
    python scripts/convert/plans_render.py --id plan_b1_arabic
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf
import yaml
from PIL import Image

from convert import pdf_text_extract as pte

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "meta" / "plans.yaml"
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def load_unit(uid: str, registry: Path = REGISTRY) -> dict:
    data = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
    for u in data.get("units", []):
        if u["id"] == uid:
            return u
    raise SystemExit(f"✗ وحدة غير معروفة: {uid}")


def render(unit: dict) -> Path:
    """يُرجع مجلد الصور بعد ضمان وجود صفحة لكل صفحة مصدر."""
    src = ROOT / unit["source"]
    img_dir = ROOT / "curriculum_raw" / f"{unit['text_dir']}_images"
    img_dir.mkdir(parents=True, exist_ok=True)

    if unit["kind"] == "pdf":
        doc = pymupdf.open(str(src))
        if doc.page_count == 0:
            raise SystemExit(f"✗ ملف تالف (0 صفحة): {unit['source']}")
        pte.render_pages(doc, unit["text_dir"], list(range(1, doc.page_count + 1)))
        return img_dir

    imgs = sorted(p for p in src.iterdir() if p.suffix.lower() in IMG_EXT)
    for n, img in enumerate(imgs, start=1):
        dest = img_dir / f"page_{n:03d}.png"
        if dest.exists() and dest.stat().st_size > 10_000:
            continue
        with Image.open(img) as im:
            im.convert("RGB").save(dest, "PNG")
    return img_dir


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", help="معرّف وحدة واحدة")
    ap.add_argument("--all", action="store_true", help="رسم كل وحدات السجل")
    ap.add_argument("--registry", default=str(REGISTRY), help="ملف السجل")
    args = ap.parse_args()

    registry = Path(args.registry)
    if args.all:
        data = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
        units = data.get("units", [])
    elif args.id:
        units = [load_unit(args.id, registry)]
    else:
        ap.error("حدّد --id أو --all")

    bad = 0
    for unit in units:
        img_dir = render(unit)
        have = len(list(img_dir.glob("page_*.png")))
        ok = have == unit["pages"]
        bad += 0 if ok else 1
        mark = "✓" if ok else "!"
        print(f"[{mark}] {unit['id']}: {have}/{unit['pages']} صورة ← {img_dir.relative_to(ROOT)}", flush=True)
    if args.all:
        print(f"[*] اكتمل: {len(units) - bad}/{len(units)}", flush=True)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
