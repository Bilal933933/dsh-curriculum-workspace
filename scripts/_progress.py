import json
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "scripts"
queue = json.loads((S / "convert" / "queue_prep_t1.json").read_text(encoding="utf-8"))
cat = {b["id"]: b for b in yaml.safe_load((ROOT / "meta" / "catalog.yaml").read_text(encoding="utf-8"))["books"]}

done_total = 0
for bid, rel, book, total, subject in queue:
    d = ROOT / "output" / book
    n = len(list(d.glob("page_*.md"))) if d.is_dir() else 0
    done_total += n
    reg = "✓ مسجَّل" if bid in cat else "—"
    print(f"{bid:30} {n:4}/{total:<4} {reg}  {book}")
print(f"المجموع: {done_total}/895 صفحة")
