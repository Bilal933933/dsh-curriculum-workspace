# -*- coding: utf-8 -*-
"""
plans_year_table.py — يلتقط رأس صفحة الجدول الأسبوعي من الأصل للتحقق من السنة.

لماذا
-----
الصفحة الأولى في كثير من الخطط ليست هي التوزيع، بل صفحة كتاب. السنة تُكتب
عادة في رأس جدول التوزيع نفسه. هذه الأداة تختار الصفحة الأكثر جدولية (فيها
عمود «الأسبوع» وأكثر صفوف)، وتقصّ أعلاها من الصورة الأصلية.

ما يقرأه
--------
`plans/text/<name>/page_*.md` (لتحديد الصفحة) و`curriculum_raw/<name>_images/`.

ما يكتبه
--------
`logs/audit/table_sheet_<n>.png`

الاستخدام
---------
    python scripts/audit/plans_year_table.py --auto "توزيع_الجغرافيا_الصف_الثاني_الثانوي" ...
    python scripts/audit/plans_year_table.py --auto --from-file meta/plans_to_check.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
TEXT = ROOT / "plans" / "text"
RAW = ROOT / "curriculum_raw"
OUT = ROOT / "logs" / "audit"

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def best_table_page(name: str) -> int | None:
    d = TEXT / name
    if not d.is_dir():
        return None
    best, score = None, -1
    for f in sorted(d.glob("page_*.md")):
        t = f.read_text(encoding="utf-8", errors="ignore")
        rows = sum(1 for ln in t.splitlines() if ln.count("|") >= 4)
        s = rows + (40 if "الأسبوع" in t else 0)
        if s > score:
            best, score = int(f.stem[5:8]), s
    return best


def crop_top(name: str, page: int, width: int = 820, ratio: float = 0.34) -> Image.Image | None:
    src = RAW / f"{name}_images" / f"page_{page:03d}.png"
    if not src.exists():
        alts = sorted((RAW / f"{name}_images").glob(f"page_{page:03d}.*"))
        if not alts:
            return None
        src = alts[0]
    with Image.open(src) as im:
        im = im.convert("RGB")
        w, h = im.size
        crop = im.crop((0, 0, w, int(h * ratio)))
    return crop.resize((width, int(crop.height * width / w)), Image.LANCZOS)


def main() -> int:
    ap = argparse.ArgumentParser(description="رأس جدول التوزيع من الأصل")
    ap.add_argument("names", nargs="*")
    ap.add_argument("--auto", action="store_true", help="اختر صفحة الجدول تلقائيًا")
    ap.add_argument("--from-file", help="ملف بأسماء الخطط، سطر لكل خطة")
    ap.add_argument("--per-sheet", type=int, default=4)
    ap.add_argument("--width", type=int, default=820)
    ap.add_argument("--ratio", type=float, default=0.34)
    args = ap.parse_args()

    names = list(args.names)
    if args.from_file:
        p = Path(args.from_file)
        if not p.is_absolute():
            p = ROOT / p
        names += [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]

    OUT.mkdir(parents=True, exist_ok=True)
    items = []
    for n in names:
        page = best_table_page(n) if args.auto else 1
        if page is None:
            print(f"[!] لا نص: {n}")
            continue
        im = crop_top(n, page, args.width, args.ratio)
        if im is None:
            print(f"[!] لا صورة أصلية: {n} ص{page}")
            continue
        items.append((f"{n[:52]}  ص{page}", im))

    made = []
    for i in range(0, len(items), args.per_sheet):
        batch = items[i:i + args.per_sheet]
        label_h, pad = 24, 8
        h = max(im.height for _, im in batch)
        sheet = Image.new("RGB", (args.width + pad * 2,
                                  len(batch) * (h + label_h + pad) + pad), "white")
        d = ImageDraw.Draw(sheet)
        for k, (label, im) in enumerate(batch):
            y = pad + k * (h + label_h + pad)
            d.text((pad + 2, y + 5), label, fill="black")
            d.line([(pad, y + label_h - 4), (pad + args.width, y + label_h - 4)], fill="red", width=2)
            sheet.paste(im, (pad, y + label_h))
        p = OUT / f"table_sheet_{len(made) + 1}.png"
        sheet.save(p, "PNG")
        made.append(p)

    for p in made:
        print(p)
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
