#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_pdf_text.py — مسبار جودة الطبقة النصية قبل التفريغ.
=========================================================
الغرض:
    قياس عيوب طبقة النص في PDF قبل تشغيل أي تفريغ، لتقرير المسار:
    نصّي مباشر أم بصري (OCR). لا يكتب في `output/` إطلاقًا.

    العيوب المقيسة (الأخطر أولًا):
    1. انقلاب لام-ألف: "األستاذ" بدل "الأستاذ" (يُفسد المطابقة المعجمية).
    2. أشكال العرض العربية (U+FB50–U+FEFF) التي لا تُطابق بعد التطبيع.
    3. حركات منفصلة عن حروفها / جدولة / نقاط قائدة (Ghostscript قديم).
    4. تمزّق الكلمات: حروف مفردة كثيرة، نصوص بلا مسافات.
    5. ترتيب بصري (سطر يبدأ بعلامة نهاية الجملة).
    6. كثافة النص: حروف عربية لكل صفحة.

الاستخدام:
    python scripts/pedagogy/probe_pdf_text.py --pdf curriculum_raw/X.pdf
    python scripts/pedagogy/probe_pdf_text.py --pdf a.pdf --pdf b.pdf --sample 12

المخرجات:
    stdout (جدول) + logs/pedagogy/probe.md
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs" / "pedagogy"

LETTER = re.compile(r"[\u0621-\u064a]")
PRESENTATION = re.compile("[\ufb50-\ufdff\ufe70-\ufeff]")
# انقلاب لام-ألف: ألف ثم همزة-ألف/همزة-إلف ثم لام، بدل لام ثم ألف.
LAM_ALEF_BAD = re.compile("[\u0627][\u0622\u0623\u0625][\u0644]")
SPACED_MARK = re.compile(r"\s[\u064b-\u0652\u0670]")
TAB = re.compile("\t")
TOKEN = re.compile(r"\S+")
UNSPACED = re.compile(r"[\u0600-\u06ff]\S{40,}")
SENT_PUNCT = ".،؛؟!:"
SAFE_ONE = {"و", "ف", "ب", "ل", "ك", "أ", "ا", "ي", "م", "ن", "ت"}


def page_metrics(text: str) -> dict:
    """يقيس صفحة واحدة ويعيد مقاييسها."""
    letters = len(LETTER.findall(text))
    tokens = TOKEN.findall(text)
    tiny = sum(1 for t in tokens if len(LETTER.findall(t)) == 1 and t not in SAFE_ONE)
    lines = [ln.strip() for ln in text.splitlines() if len(LETTER.findall(ln)) >= 8]
    visual_starts = sum(1 for ln in lines if ln[0] in SENT_PUNCT)
    return {
        "letters": letters,
        "presentation": len(PRESENTATION.findall(text)),
        "lam_alef_bad": len(LAM_ALEF_BAD.findall(text)),
        "spaced_marks": len(SPACED_MARK.findall(text)),
        "tabs": len(TAB.findall(text)),
        "tiny_ratio": (tiny / len(tokens)) if tokens else 0.0,
        "unspspaced": len(UNSPACED.findall(text)),
        "visual_ratio": (visual_starts / len(lines)) if lines else 0.0,
        "lines": len(lines),
        "text": text,
    }


def decide(m: dict, total_letters: int) -> tuple[str, list[str]]:
    """يقرر حكم الصفحة: نصّي | نصّي بعد إصلاح | بصري."""
    notes: list[str] = []
    if m["letters"] < 40:
        return "بصري", ["صفحة شبه فارغة"]
    if m["presentation"]:
        notes.append(f"أشكال عرض×{m['presentation']}")
    if m["spaced_marks"] >= 3:
        notes.append(f"حركات منفصلة×{m['spaced_marks']}")
    if m["tabs"] >= 3:
        notes.append(f"جدولة×{m['tabs']}")
    if m["tiny_ratio"] > 0.15:
        notes.append(f"حروف مفردة {m['tiny_ratio']:.0%}")
    if m["visual_ratio"] >= 0.5:
        notes.append("ترتيب بصري")
    if total_letters and m["lam_alef_bad"] / total_letters > 0.005:
        notes.append(f"انقلاب لام-ألف×{m['lam_alef_bad']}")

    fatal = [n for n in notes if n.startswith(("حركات منفصلة", "جدولة", "حروف مفردة", "ترتيب بصري"))]
    if fatal:
        return "بصري", notes
    if notes:
        return "نصّي+إصلاح", notes
    return "نصّي", notes


def probe(pdf: Path, sample: int) -> dict:
    doc = pymupdf.open(str(pdf))
    n = doc.page_count
    # عيّنة موزّعة + أول/آخر صفحتين.
    idx = sorted({1, 2, n - 1, n} | {max(1, round(n * k / sample)) for k in range(1, sample + 1)})
    idx = [i for i in idx if 1 <= i <= n]

    rows = []
    for p in idx:
        raw = doc[p - 1].get_text("text")
        norm = unicodedata.normalize("NFKC", raw) if PRESENTATION.search(raw) else raw
        m = page_metrics(norm)
        rows.append((p, m))
        m["text"] = ""

    letters = [m["letters"] for _, m in rows]
    total = sum(letters)
    avg = total / len(rows) if rows else 0
    pres = sum(m["presentation"] for _, m in rows)
    lam = sum(m["lam_alef_bad"] for _, m in rows)
    spaced = sum(m["spaced_marks"] for _, m in rows)
    tabs = sum(m["tabs"] for _, m in rows)
    tiny = sum(m["tiny_ratio"] for _, m in rows) / len(rows) if rows else 0
    unsps = sum(m["unspspaced"] for _, m in rows)
    visual = sum(1 for _, m in rows if m["visual_ratio"] >= 0.5)

    verdicts = {}
    for p, m in rows:
        v, notes = decide(m, total)
        verdicts[p] = (v, notes)

    score_bad = sum(1 for v, _ in verdicts.values() if v == "بصري")
    doc.close()
    return {
        "file": pdf.name,
        "pages": n,
        "sampled": len(rows),
        "avg_letters": avg,
        "min_letters": min(letters) if letters else 0,
        "presentation": pres,
        "lam_alef": lam,
        "lam_alef_rate": (lam / total) if total else 0,
        "spaced_marks": spaced,
        "tabs": tabs,
        "tiny": tiny,
        "unspaced": unsps,
        "visual_pages": visual,
        "need_vision": score_bad,
        "verdicts": verdicts,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="مسبار جودة الطبقة النصية لملفات PDF")
    ap.add_argument("--pdf", action="append", required=True, help="مسار PDF (يتكرر)")
    ap.add_argument("--sample", type=int, default=10, help="عدد الصفحات في العيّنة")
    args = ap.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for p in args.pdf:
        pdf = Path(p)
        if not pdf.is_absolute():
            pdf = ROOT / pdf
        if not pdf.is_file():
            print(f"[!] لا يوجد: {pdf}")
            return 2
        r = probe(pdf, args.sample)
        results.append(r)
        print(f"[✓] {r['file']}: {r['pages']} ص | متوسط {r['avg_letters']:.0f} حرف/ص "
              f"| لام-ألف {r['lam_alef_rate']:.2%} | بصري {r['need_vision']}/{r['sampled']}")

    lines = [
        "# مسبار جودة الطبقة النصية",
        "",
        "| الملف | صفحات | عيّنة | متوسط حروف | أدنى | أشكال عرض | انقلاب لام-ألف | معدله | حركات منفصلة | جدولة | حروف مفردة | بلا مسافات | بصري | يحتاج بصريًا |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['file']} | {r['pages']} | {r['sampled']} | {r['avg_letters']:.0f} | {r['min_letters']} | "
            f"{r['presentation']} | {r['lam_alef']} | {r['lam_alef_rate']:.2%} | {r['spaced_marks']} | "
            f"{r['tabs']} | {r['tiny']:.0%} | {r['unspaced']} | {r['visual_pages']} | {r['need_vision']} |"
        )
    lines += ["", "## أحكام الصفحات المفحوصة", ""]
    for r in results:
        lines.append(f"### {r['file']}")
        lines.append("")
        for p, (v, notes) in sorted(r["verdicts"].items()):
            lines.append(f"- ص {p}: **{v}** — {', '.join(notes) if notes else 'سليم'}")
        lines.append("")
    (LOG_DIR / "probe.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[*] التقرير: logs/pedagogy/probe.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
