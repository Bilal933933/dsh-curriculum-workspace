#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eval_retrieval.py — يقيس جودة الاسترجاع مقابل meta/gold.json

لماذا
-----
كان عندنا حارس للأنابيب (`toc_review.py --validate`) ولا مقابل لسؤال المعلم:
«هل يعيد السؤال صفحته؟». هذا السكربت يعطي رقمًا بدل الانطباع.

الطريقة
--------
- لكل سؤال: نُطبّع عبارته، ونقيس كل صفحة بوزن IDF لكل كلمة:
  ظهورها في عنوان الصفحة (`headings_draft.tsv`) يزن 6×، وفي متنها 1×.
- الترتيب تنازليًا بالوزن، وعند التعادل تُرجَّح الصفحة الأقصر (كثافة).
- المقياس: hit@1، hit@k، MRR. المرجع صفحة الموضوع في `toc.yaml`.

الاستخدام
---------
    python scripts/eval_retrieval.py
    python scripts/eval_retrieval.py --k 5 --verbose
    python scripts/eval_retrieval.py --json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "retrieval"))
from build_index import normalize  # noqa: E402

GOLD = ROOT / "meta" / "gold.json"
BOOKS_META = ROOT / "meta" / "books"
INDEX = ROOT / "index"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def index_dir(book: str) -> Path | None:
    toc = BOOKS_META / book / "toc.yaml"
    if not toc.exists():
        return None
    m = re.search(r'^index_dir: "(.+)"$', toc.read_text(encoding="utf-8-sig"), re.M)
    return INDEX / m.group(1).split("/", 1)[1] if m else None


def tokens(text: str) -> list[str]:
    seen, out = set(), []
    for t in normalize(text).split():
        if len(t) >= 3 and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def load_book(book: str) -> dict:
    """يعيد {page: (body_norm, set(heading_tokens), len(body), df_index)}."""
    d = index_dir(book)
    pages: dict[int, dict] = {}
    if not d or not d.is_dir():
        return pages
    headings: dict[int, set[str]] = {}
    tsv = d.parent / "headings_draft.tsv"
    if tsv.exists():
        for line in tsv.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[0].isdigit():
                headings.setdefault(int(parts[0]), set()).update(normalize(parts[2]).split())

    df: dict[str, int] = {}
    for p in d.glob("page_*.txt"):
        m = re.search(r"(\d+)", p.stem)
        if not m:
            continue
        body = normalize(p.read_text(encoding="utf-8", errors="ignore"))
        page = int(m.group(1))
        hset = headings.get(page, set())
        pages[page] = {"body": body, "head": hset, "len": len(body)}
        for t in set(body.split()) | hset:
            df[t] = df.get(t, 0) + 1
    pages["_n"] = len(pages)
    pages["_df"] = df
    return pages


def rank(query: str, pages: dict, take: int) -> list[int]:
    toks = tokens(query)
    if not toks or not pages.get("_n"):
        return []
    n, df = pages["_n"], pages["_df"]
    scored = []
    for page, info in pages.items():
        if not isinstance(page, int):
            continue
        score = 0.0
        for t in toks:
            if t in info["head"]:
                score += 6.0 * math.log(1 + n / (1 + df.get(t, 0)))
            elif t in info["body"]:
                score += math.log(1 + n / (1 + df.get(t, 0)))
        if score:
            scored.append((score, -info["len"], page))
    scored.sort(reverse=True)
    return [p for _, _, p in scored[:take]]


def main() -> int:
    ap = argparse.ArgumentParser(description="قياس الاسترجاع مقابل gold.json")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not GOLD.exists():
        print("[!] لا gold.json — نفّذ بناءه أولًا")
        return 2
    items = json.loads(GOLD.read_text(encoding="utf-8"))["items"]

    cache: dict[str, dict] = {}
    per_book: dict[str, list[float]] = {}
    misses = []
    for it in items:
        book = it["book"]
        if book not in cache:
            cache[book] = load_book(book)
        top = rank(it["query"], cache[book], args.k)
        expected = it["expected_page"]
        rr = 1.0 / (top.index(expected) + 1) if expected in top else 0.0
        if rr == 0.0:
            misses.append((it["id"], book, expected, top[:3]))
        per_book.setdefault(book, []).append(rr)

    def stats(vals: list[float]) -> tuple[float, float, float]:
        n = len(vals) or 1
        return (
            sum(1 for v in vals if v == 1.0) / n,
            sum(1 for v in vals if v > 0) / n,
            sum(vals) / n,
        )

    allv = [v for vs in per_book.values() for v in vs]
    h1, hk, mrr = stats(allv)
    if args.json:
        print(json.dumps({
            "n": len(allv), "k": args.k,
            "hit@1": round(h1, 4), "hit@k": round(hk, 4), "mrr": round(mrr, 4),
            "per_book": {b: dict(zip(("hit@1", "hit@k", "mrr"),
                                     (round(x, 4) for x in stats(v))))
                         for b, v in per_book.items()},
            "misses": [{"id": i, "book": b, "expected": e, "top": t} for i, b, e, t in misses],
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"عدد الأسئلة: {len(allv)} | k={args.k}")
    print(f"{'الكتاب':<18} {'n':>3} {'hit@1':>7} {'hit@'+str(args.k):>7} {'MRR':>7}")
    for b, v in sorted(per_book.items()):
        bh1, bhk, bm = stats(v)
        print(f"{b:<18} {len(v):>3} {bh1:>7.2f} {bhk:>7.2f} {bm:>7.2f}")
    print("-" * 46)
    print(f"{'الإجمالي':<18} {len(allv):>3} {h1:>7.2f} {hk:>7.2f} {mrr:>7.2f}")
    if args.verbose and misses:
        print("\nإخفاقات (المتوقع ← أول 3 مرشحين):")
        for i, b, e, t in misses:
            print(f"  {i} {b}: {e} ← {t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
