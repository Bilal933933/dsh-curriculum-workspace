#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline_official_plans.py — تفريغ توزيعات المناهج الرسمية (طبقة صور ← Vision) وترتيبها.

لماذا
-----
PDF توزيعات الوزارة ممسوحة (بلا طبقة نص)، فالتفريغ لا بد أن يمرّ بالصور:
`render` (pymupdf ← PNG) ثم `run_vision_batch.py` (Gemini) ثم نقل الناتج من
`output/<text_dir>` إلى الطبقة الصحيحة `plans/official/<مرحلة>/<صف>/<مادة>/`.

الاستخدام
---------
    python scripts/convert/pipeline_official_plans.py --limit 1
    python scripts/convert/pipeline_official_plans.py --only plan_of_010
    python scripts/convert/pipeline_official_plans.py            # الكل
    python scripts/convert/pipeline_official_plans.py --dry-run

ملاحظات
-------
- قابل للاستئناف: يتخطى وحدة اكتملت صفحاتها في `plans/official`.
- يحدّث `meta/plans_official.yaml` بعد كل وحدة (status / pages_converted).
- لا يحذف شيئًا: الوحدات الناقصة تبقى في `output/` للمحاولة التالية.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from plans_render import render  # noqa: E402

REGISTRY = ROOT / "meta" / "plans_official.yaml"
OUTPUT = ROOT / "output"
PLANS = ROOT / "plans" / "official"
LOG = ROOT / "logs" / "plans_official.log"

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def target_dir(unit: dict) -> Path:
    return PLANS / unit["stage"] / unit["grade"] / unit["subject"]


def save_registry(units: list[dict]) -> None:
    REGISTRY.write_text(
        yaml.safe_dump({"version": 1, "units": units}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def count_pages(d: Path) -> int:
    return len(list(d.glob("page_*.md"))) if d.is_dir() else 0


def convert(unit: dict, workers: int, timeout: int) -> tuple[int, str]:
    """يرسم ثم يفرّغ. يعيد (عدد الصفحات المفرّغة، ملاحظة)."""
    img_dir = render(unit)
    have = len(list(img_dir.glob("page_*.png")))
    if have != unit["pages"]:
        return 0, f"صور ناقصة {have}/{unit['pages']}"
    cmd = [
        sys.executable, str(ROOT / "scripts" / "convert" / "run_vision_batch.py"),
        "--book", unit["text_dir"], "--start", "1", "--end", str(unit["pages"]),
        "--workers", str(workers), "--timeout", str(timeout),
    ]
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    note = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()[-1:] or [""]
    return count_pages(OUTPUT / unit["text_dir"]), note[0][:120]


def main() -> int:
    ap = argparse.ArgumentParser(description="تفريغ توزيعات المناهج الرسمية")
    ap.add_argument("--only", help="معرّف وحدة واحدة")
    ap.add_argument("--limit", type=int, default=0, help="أقصى عدد وحدات (0 = الكل)")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--force", action="store_true", help="أعد التفريغ حتى لو اكتمل")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    units = data.get("units", [])

    queue = []
    for u in units:
        if args.only and u["id"] != args.only:
            continue
        if not args.force and count_pages(target_dir(u)) >= u["pages"] > 0:
            u["status"] = "converted"
            continue
        queue.append(u)
    if args.limit:
        queue = queue[: args.limit]

    log(f"قائمة العمل: {len(queue)} وحدة | صفحات: {sum(u['pages'] for u in queue)}")
    if args.dry_run:
        for u in queue:
            print(f"   {u['id']} | {u['text_dir']} | {u['pages']} ص")
        return 0

    done = failed = 0
    for i, u in enumerate(queue, start=1):
        mark = f"[{i}/{len(queue)}]"
        pages, note = convert(u, args.workers, args.timeout)
        if pages >= u["pages"] > 0:
            dst = target_dir(u)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                shutil.rmtree(dst)
            shutil.move(str(OUTPUT / u["text_dir"]), str(dst))
            u["status"], u["pages_converted"] = "converted", pages
            done += 1
            log(f"{mark} ✓ {u['text_dir']} ({pages} ص) → {dst.relative_to(ROOT)}")
        else:
            u["status"], u["pages_converted"] = "partial", pages
            failed += 1
            log(f"{mark} ! {u['text_dir']} ({pages}/{u['pages']}) — {note}")
        save_registry(units)

    log(f"انتهى: ناجح {done} | ناقص {failed} | المتبقي {len(queue) - done - failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
