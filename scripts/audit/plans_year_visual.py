# -*- coding: utf-8 -*-
"""
plans_year_visual.py — لقطة بصرية من الملفات الأصلية للتحقق من سنة التوزيع.

لماذا
-----
التفريغ قد يُسقط السنة أو يقرأها خطأ. السنة الحقيقية تُقرأ من الصورة الأصلية
(`curriculum_raw/<plan>_images/page_001.png`)، وهذه الأداة تقصّ أعلى الصفحة
الأولى (موضع العنوان والسنة) وتكوّم عدة خطط في صورة واحدة للمراجعة بالعين.

ما يقرأه
--------
`curriculum_raw/<name>_images/page_001.png` أو `<name>.pdf`.

ما يكتبه
--------
`logs/audit/year_sheet_<n>.png`

الاستخدام
---------
    python scripts/audit/plans_year_visual.py --names "توزيع_الجغرافيا_..." "توزيع_التاريخ_..."
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "curriculum_raw"
OUT = ROOT / "logs" / "audit"

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def first_page_image(name: str, width: int = 760) -> Image.Image | None:
    """أعلى الصفحة الأولى (45%) من صور الخطة أو من PDF إن لم توجد الصور."""
    img_dir = RAW / f"{name}_images"
    if img_dir.is_dir():
        pngs = sorted(img_dir.glob("page_001.*"))
        if pngs:
            with Image.open(pngs[0]) as im:
                im = im.convert("RGB")
                w, h = im.size
                crop = im.crop((0, 0, w, int(h * 0.45)))
                return crop.resize((width, int(crop.height * width / w)), Image.LANCZOS)
    pdf = RAW / f"{name}.pdf"
    if pdf.is_file():
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        zoom = width / page.rect.width
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        doc.close()
        return im.crop((0, 0, im.width, int(im.height * 0.45)))
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="لقطة سنوية من الأصل")
    ap.add_argument("--names", nargs="+", required=True)
    ap.add_argument("--per-sheet", type=int, default=5)
    ap.add_argument("--width", type=int, default=760)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    imgs = []
    for n in args.names:
        im = first_page_image(n, args.width)
        if im is None:
            print(f"[!] لا صورة أصلية: {n}")
            continue
        imgs.append((n, im))

    made = []
    for i in range(0, len(imgs), args.per_sheet):
        batch = imgs[i:i + args.per_sheet]
        label_h, pad = 26, 10
        h = max(im.height for _, im in batch)
        sheet = Image.new("RGB", (args.width + pad * 2,
                                  len(batch) * (h + label_h + pad) + pad), "white")
        d = ImageDraw.Draw(sheet)
        for k, (name, im) in enumerate(batch):
            y = pad + k * (h + label_h + pad)
            sheet.paste(im, (pad, y + label_h))
            d.text((pad + 2, y + 6), name[:70], fill="black")
            d.line([(pad, y + label_h - 4), (pad + args.width, y + label_h - 4)], fill="red", width=2)
        p = OUT / f"year_sheet_{len(made) + 1}.png"
        sheet.save(p, "PNG")
        made.append(p)

    for p in made:
        print(p)
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
