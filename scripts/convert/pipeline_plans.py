#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pipeline_plans.py — تفريغ توزيعات المناهج: 3 وحدات متزامنة + تحديث السجل فورًا.

لكل وحدة: رسم الصور ← تفريغ الرؤية ← إعادة الصفحات الفاشلة ← تحديث meta/plans.yaml.

الترتيب: التوزيعات الرسمية المختومة أولًا، ثم المستخرجة من كتب الأضواء.

الاستخدام (من مجلد workspace):
    python scripts/convert/pipeline_plans.py                 # كل المتبقي
    python scripts/convert/pipeline_plans.py --only official # الرسمي فقط
    python scripts/convert/pipeline_plans.py --limit 5
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "meta" / "plans.yaml"
OUT = ROOT / "output"
LOG = ROOT / "logs" / "plans.log"

MAX_PARALLEL = 3
VISION_WORKERS = 2
MAX_RETRY_ROUNDS = 3

_lock = threading.Lock()

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with _lock:
        print(line, flush=True)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def run(cmd: list[str]) -> int:
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        tail = ((p.stdout or "") + (p.stderr or ""))[-400:]
        log(f"    ↳ تحذير (code {p.returncode}): {tail.strip()[:300]}")
    return p.returncode


def load_units() -> list[dict]:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    return data.get("units", [])


def save_units(units: list[dict]) -> None:
    REGISTRY.write_text(
        yaml.safe_dump({"version": 1, "units": units}, allow_unicode=True,
                       sort_keys=False, width=200),
        encoding="utf-8")


def update(uid: str, **fields) -> None:
    with _lock:
        units = load_units()
        for u in units:
            if u["id"] == uid:
                u.update(fields)
                break
        save_units(units)


def md_pages(text_dir: str) -> dict[int, Path]:
    d = OUT / text_dir
    res: dict[int, Path] = {}
    if not d.is_dir():
        return res
    for f in d.glob("page_*.md"):
        try:
            res[int(f.stem.split("_")[1])] = f
        except (IndexError, ValueError):
            continue
    return res


def process(unit: dict) -> str:
    uid, td, total = unit["id"], unit["text_dir"], unit["pages"]
    t0 = time.time()
    log(f"▶ {uid} ({total} صفحة) — {unit['title'][:60]}")

    update(uid, status="running")
    if run([sys.executable, "scripts/convert/plans_render.py", "--id", uid]) != 0:
        update(uid, status="pending", note="فشل الرسم")
        return f"{uid}: فشل الرسم"

    run([sys.executable, "scripts/convert/run_vision_batch.py", "--book", td,
         "--start", "1", "--end", str(total), "--workers", str(VISION_WORKERS)])

    for rnd in range(1, MAX_RETRY_ROUNDS + 1):
        files = md_pages(td)
        bad = [n for n in range(1, total + 1)
               if n not in files or files[n].stat().st_size == 0]
        if not bad:
            break
        log(f"  ↻ {uid}: جولة إصلاح {rnd} — {len(bad)} صفحة")
        for n in bad:
            f = files.get(n)
            if f is not None:
                f.unlink(missing_ok=True)
            run([sys.executable, "scripts/convert/run_vision_batch.py", "--book", td,
                 "--start", str(n), "--end", str(n), "--workers", "1"])

    files = md_pages(td)
    missing = [n for n in range(1, total + 1) if n not in files]
    status = "converted" if not missing else "partial"
    update(uid, status=status, pages_converted=len(files),
           note=(f"ناقص {missing[:10]}" if missing else None))
    mins = (time.time() - t0) / 60
    log(f"✓ {uid}: {len(files)}/{total} صفحة | {mins:.0f} دقيقة")
    return f"{uid}: {len(files)}/{total}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["official", "derived"], default=None)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    units = [u for u in load_units()
             if u["status"] not in ("converted", "broken")
             and (args.only is None or u["authority"] == args.only)]
    # الرسمي أولًا، ثم المستخرج؛ وداخل كل منهما بالمعرّف
    units.sort(key=lambda u: (u["authority"] != "official", u["id"]))
    if args.limit:
        units = units[: args.limit]
    if not units:
        log("لا وحدات متبقية.")
        return 0

    log("=" * 60)
    log(f"بدء تفريغ التوزيعات: {len(units)} وحدة | تزامن {MAX_PARALLEL} | "
        f"{sum(u['pages'] for u in units)} صفحة")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as ex:
        futs = {ex.submit(process, u): u for u in units}
        for fut in as_completed(futs):
            u = futs[fut]
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                log(f"✗ انهيار {u['id']}: {exc}")
                update(u["id"], status="pending", note=f"انهيار: {exc}")
                results.append(f"{u['id']}: انهيار")

    log("-" * 60)
    for r in results:
        log("   " + r)
    log("انتهت دفعة التوزيعات.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
