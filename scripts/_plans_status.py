"""_plans_status.py — عرض حالة وحدات meta/plans.yaml (قراءة فقط)."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "meta" / "plans.yaml"


def main() -> int:
    data = yaml.safe_load(REG.read_text(encoding="utf-8")) or {}
    units = data.get("units", [])
    only = sys.argv[1] if len(sys.argv) > 1 else None

    todo = [u for u in units if u.get("status") != "converted"]
    print(f"إجمالي الوحدات: {len(units)} | غير مكتملة: {len(todo)}")
    print(f"{'الحالة':10} {'الجهة':9} {'صفحات':>7}  {'المعرّف':30} ملاحظة")
    for u in units:
        if only and u.get("status") != only:
            continue
        if not only and u.get("status") == "converted":
            continue
        done = u.get("pages_converted")
        done = "-" if done is None else str(done)
        print(f"{u['status']:10} {u['authority']:9} {done:>3}/{u['pages']:<3}  "
              f"{u['id']:30} {u.get('note') or ''}")

    total_pages = sum(u["pages"] for u in units)
    done_pages = sum(len(list((ROOT / 'output' / u['text_dir']).glob('page_*.md')))
                     if (ROOT / 'output' / u['text_dir']).is_dir() else 0
                     for u in units)
    print(f"\nالصفحات: {done_pages}/{total_pages}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
