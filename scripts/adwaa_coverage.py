#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
جدول تغطية المواد لكل مرحلة من المانيفست.

مخرج واحد: workspace/logs/adwaa_coverage.md (جدول Markdown)
يُلصق مباشرة في الرد على المستخدم.
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifest" / "adwaa_manifest.json"
LOGS = ROOT / "logs"

ORDER = ["kg1", "kg2", "p1", "p2", "p3", "p4", "p5", "p6",
         "m1", "m2", "m3", "s1", "s2", "s3"]
STAGE_NAME = {
    "kg1": "روضة ١", "kg2": "روضة ٢", "p1": "ابتدائي ١", "p2": "ابتدائي ٢",
    "p3": "ابتدائي ٣", "p4": "ابتدائي ٤", "p5": "ابتدائي ٥", "p6": "ابتدائي ٦",
    "m1": "متوسط ١", "m2": "متوسط ٢", "m3": "متوسط ٣",
    "s1": "ثانوي ١", "s2": "ثانوي ٢", "s3": "ثانوي ٣",
}


def main():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cov: dict[str, set] = defaultdict(set)
    counts: dict[str, int] = defaultdict(int)
    for e in m:
        g = e["gkey"]
        cov[g].add(e["subject"])
        counts[g] += 1

    # ترتيب المواد حسب أول ظهور في المانيفست (استقرار قابل للقراءة)
    subs = list(dict.fromkeys(e["subject"] for e in m if e["subject"]))

    lines = [
        f"إجمالي الملفات في المانيفست: **{len(m)}**",
        "",
        "| المادة | " + " | ".join(STAGE_NAME[g] for g in ORDER) + " |",
        "|" + "---|" * (len(ORDER) + 1),
    ]
    for s in subs:
        cells = ["✔" if s in cov[g] else "✗" for g in ORDER]
        lines.append(f"| {s} | " + " | ".join(cells) + " |")
    lines.append("| **عدد الملفات** | " + " | ".join(str(counts[g]) for g in ORDER) + " |")

    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "adwaa_coverage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("")


if __name__ == "__main__":
    main()
