#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_book.py — تفريغ كتاب تربوي بالمسار النصي مع إصلاح ودقّة مُقاسة.
======================================================================
لماذا
-----
كتب PDF الرقمية قد تحمل طبقة نص معطوبة (قلب حروف، ترميز خطّ مكسور).
هذا السكربت يفرّغها نصيًا ثم يُصلحها بقيادة المعجم، **ويقيس جودة كل صفحة**
قبل كتابتها. وإن كان الكتاب كله تحت الحد ⇒ يرفض ويوصي بالتحويل البصري.

بوابة الجودة
------------
    نسبة الكلمات الصحيحة في الصفحة ≥ `--min-validity` (افتراضي 0.85)
    وإلا تُسجَّل في `logs/pedagogy/ocr_needed_<book>.txt` للتحويل البصري.

المخرجات
--------
    output/<book>/page_XXX.md                     النص المُصلَح
    logs/pedagogy/extract_<book>.md               تقرير الجودة صفحة بصفحة
    logs/pedagogy/ocr_needed_<book>.txt           الصفحات التي تحتاج بصريًا

الاستخدام
----------
    python scripts/pedagogy/extract_book.py --pdf "curriculum_raw/X.pdf" --book "X"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "retrieval"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_text_quality as A  # noqa: E402
import repair_text as R  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

WS = re.compile(r"[ \t]{2,}")


def clean(text: str) -> str:
    """يضبط المسافات ويحذف الأسطر الفارغة المتكررة."""
    lines = [WS.sub(" ", ln).strip() for ln in text.splitlines()]
    out, blank = [], 0
    for ln in lines:
        if ln:
            blank = 0
            out.append(ln)
        else:
            blank += 1
            if blank == 1:
                out.append("")
    return "\n".join(out).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="تفريغ نصي مُصلَح بقيادة المعجم")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--min-validity", type=float, default=0.85, help="حد قبول الصفحة")
    ap.add_argument("--min-book", type=float, default=0.85, help="حد قبول الكتاب كله")
    ap.add_argument("--force", action="store_true", help="الكتابة رغم ضعف الجودة")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    if not pdf.is_absolute():
        pdf = ROOT / pdf
    if not pdf.is_file():
        print(f"[!] لا يوجد: {pdf}")
        return 2

    vocab = A.load_vocab()
    if not vocab:
        print("[!] ابنِ المعجم أولًا: audit_text_quality.py --build-vocab")
        return 2

    doc = pymupdf.open(str(pdf))
    total = doc.page_count
    out_dir = ROOT / "output" / args.book
    out_dir.mkdir(parents=True, exist_ok=True)
    LOG = ROOT / "logs" / "pedagogy"
    LOG.mkdir(parents=True, exist_ok=True)

    rows, need_ocr, changes_total = [], [], 0
    for p in range(1, total + 1):
        raw = doc[p - 1].get_text("text")
        fixed, st = R.repair(raw, vocab)
        page = clean(fixed)
        ev = A.evaluate_page(page, vocab)
        rows.append((p, ev, st, page))
        changes_total += st.get("fixed", 0)
        if ev["rate"] < args.min_validity and ev["letters"] >= 40:
            need_ocr.append(p)
    doc.close()

    vals = [ev["rate"] for _, ev, _ in rows if ev["tokens"]]
    overall = sum(ev["valid"] for _, ev, _, _ in rows) / max(1, sum(ev["tokens"] for _, ev, _, _ in rows))
    vals_sorted = sorted(vals)
    median = vals_sorted[len(vals_sorted) // 2] if vals_sorted else 0

    if overall < args.min_book and not args.force:
        report = LOG / f"extract_{args.book}.md"
        report.write_text(
            f"# تفريغ نصي مرفوض — {args.book}\n\n"
            f"- الصفحات: {total}\n- نسبة الكلمات الصحيحة: {overall:.2%}\n"
            f"- الوسيط: {median:.2%}\n- الحكم: مرفوض، يحتاج تحويلًا بصريًا\n",
            encoding="utf-8")
        (LOG / f"ocr_needed_{args.book}.txt").write_text(
            "\n".join(map(str, range(1, total + 1))) + "\n", encoding="utf-8")
        print(f"[⛔] {args.book}: {overall:.2%} < الحد {args.min_book:.0%} — رُفض ولم تُكتب صفحات.")
        print(f"     التقرير: {report.relative_to(ROOT)}")
        return 3

    for p, ev, st, page in rows:
        if ev["letters"] >= 40 or page:
            (out_dir / f"page_{p:03d}.md").write_text(page + "\n", encoding="utf-8")

    lines = [
        f"# تفريغ نصي — {args.book}",
        "",
        f"- **الصفحات:** {total} | **الكلمات المُصلَحة:** {changes_total:,}",
        f"- **نسبة الكلمات الصحيحة:** {overall:.2%} | الوسيط {median:.2%} | الأدنى {vals_sorted[0]:.1%}" if vals_sorted else "",
        f"- **حد القبول للصفحة:** {args.min_validity:.0%} | **تحتاج بصريًا:** {len(need_ocr)} صفحة",
        f"- **الحكم:** {'مقبول' if overall >= args.min_book else 'مرفوض — يُحوَّل بصريًا'}",
        "",
        "| صفحة | كلمات | صحيحة | النسبة | مُصلَح | ملتبس | بقي | الحكم |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for p, ev, st, page in rows:
        flag = "✅" if ev["rate"] >= args.min_validity else "⚠️"
        lines.append(f"| {p} | {ev['tokens']} | {ev['valid']} | {ev['rate']:.1%} | "
                     f"{st.get('fixed', 0)} | {st.get('ambiguous', 0)} | {st.get('left', 0)} | {flag} |")
    (LOG / f"extract_{args.book}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (LOG / f"ocr_needed_{args.book}.txt").write_text(
        "\n".join(map(str, need_ocr)) + ("\n" if need_ocr else ""), encoding="utf-8")

    print(f"[*] {args.book}: {total} صفحة | صحيحة {overall:.2%} | وسيط {median:.2%} | "
          f"مُصلَح {changes_total:,} | تحتاج بصريًا {len(need_ocr)}")
    if overall < args.min_book and not args.force:
        print(f"[⛔] الجودة تحت الحد ({args.min_book:.0%}) — الكتاب يحتاج تحويلًا بصريًا.")
        print(f"     التقرير: logs/pedagogy/extract_{args.book}.md")
        return 3
    print(f"[✓] كُتب: output/{args.book}/page_*.md")
    print(f"[*] التقرير: logs/pedagogy/extract_{args.book}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
