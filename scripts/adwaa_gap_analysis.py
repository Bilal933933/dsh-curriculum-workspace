#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
تحليل الفجوات: لماذا بعض (مرحلة، مادة) غير موجودة في المانيفست؟

يركض نفس استعلامي البحث، ويحسب لكل مستند أي حاجب استبعه:
  1) ليس في عنوانه "الاضواء"
  2) لا يطابق ترم 1 / كتاب كامل (TERM1)
  3) يطابق ترم 2 أو غيره (TERM2)
  4) يطابق كلمات غير الكتب (NOT_BOOK)
  5) نجى الحواجب لكن التصنيف لم يحدد مرحلة (بلا gkey)
  6) نجى ونُصنف — فهذه لطخات (مرحلة، مادة) «متاح نظرياً»

الكتابة: workspace/logs/adwaa_gap_analysis.md
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adwaa_tawzee3 import (TERM1, TERM2, NOT_BOOK, classify,  # noqa: E402
                           norm, season_score, search_all)

LOGS = ROOT / "logs"


def main():
    queries = [
        'title:(الاضواء) AND mediatype:texts',
        'title:(الاضواء) AND title:(ترم) AND mediatype:texts',
    ]
    docs, seen = [], set()
    for q in queries:
        for d in search_all(q):
            did = d.get("identifier")
            if did and did not in seen:
                seen.add(did)
                docs.append(d)

    buckets = defaultdict(list)
    for d in docs:
        t = norm(d.get("title", ""))
        if "الاضواء" not in t and "اضواء" not in t:
            buckets["بلا اسم الكتاب"].append(d.get("title", ""))
            continue
        if not any(k in t for k in TERM1):
            buckets["ليس ترم1/كتاب-كامل"].append(d.get("title", ""))
            continue
        if any(k in t for k in TERM2):
            buckets["ترم2 (مقصوم عمداً)"].append(d.get("title", ""))
            continue
        if any(k in t for k in NOT_BOOK):
            buckets["غير-كتاب (أعمال/امتحانات)"].append(d.get("title", ""))
            continue
        gkey, _stage, _grade, subj = classify(t)
        if not gkey:
            buckets["نجى لائقًا لكن بلا مرحلة"].append(d.get("title", ""))
            continue
        buckets[f"متاح: {gkey}|{subj}"].append(d.get("title", ""))

    lines = [f"مجموع المستندات الفريدة: {len(docs)}", ""]
    for name in sorted(buckets, key=lambda k: -len(buckets[k])):
        items = buckets[name]
        lines.append(f"## {name} — {len(items)}")
        for i in items[:40]:
            lines.append(f"- {i}")
        if len(items) > 40:
            lines.append(f"- … ({len(items) - 40} أخرى)")
        lines.append("")

    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "adwaa_gap_analysis.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
