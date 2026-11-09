#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_text_quality.py — تدقيق موضوعي لجودة النص المستخرج من PDF.
===============================================================
الفكرة:
    لا نحكم على النص بالعين، بل بمقياس: **نسبة الكلمات الصحيحة**.
    يُبنى معجم من كتب المستودع المفهرسة (`index/*/norm/*.txt`) ثم تُقاس كل
    صفحة PDF بنسبة كلماتها الموجودة في المعجم. النص المشوَّه (`اؼبعرفة`)
    لا يطابق شيئًا؛ النص السليم يطابق 90%+ .

الأنماط:
    --build-vocab            يبني معجم المراجع ويحفظه في cache/pedagogy/vocab.txt
    --pdf X [--pdf Y] --all  يدقّق كل صفحات الكتب المحددة
    --pdf X --pages 1-20     يدقّق مدى صفحات

الإصلاحات المطبّقة قبل القياس (حتمية ومُحصاة):
    R1 حركة منفصلة عن حرفها: "مُ حَمَّد" ← "مُحَمَّد"   (حذف مسافة قبل الحركة)
    R2 انقلاب لام-ألف:        "األستاذ"     ← "الأستاذ"  (تبديل موضع اللام)
    R3 أشكال العرض:          NFKC          ← حروف أساس

المخرجات:
    logs/pedagogy/audit_<stem>.md   تقرير تفصيلي
    logs/pedagogy/audit_summary.json ملخّص آلي لكل كتاب

الاستخدام:
    python scripts/pedagogy/audit_text_quality.py --build-vocab
    python scripts/pedagogy/audit_text_quality.py --pdf curriculum_raw/X.pdf --all
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "retrieval"))
from build_index import normalize  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

CACHE = ROOT / "cache" / "pedagogy"
VOCAB = CACHE / "vocab.txt.gz"
LOG_DIR = ROOT / "logs" / "pedagogy"

LETTER = re.compile(r"[\u0621-\u064a]")
PRESENTATION = re.compile("[\ufb50-\ufdff\ufe70-\ufeff]")
SPACED_MARK = re.compile(r"[ \t]([\u064b-\u0652\u0670])")
LAM_ALEF_BAD = re.compile("([\u0627])([\u0622\u0623\u0625])([\u0644])")
TAB = re.compile("\t")


# ------------------------------------------------------------------ المعجم
def build_vocab(min_freq: int = 2) -> dict:
    """يبني معجمًا تكراريًا من فهارس المستودع المطبَّعة."""
    counter: Counter[str] = Counter()
    files = list((ROOT / "index").glob("*/norm/page_*.txt"))
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        counter.update(t for t in text.split() if len(t) >= 3 and len(LETTER.findall(t)) >= 3)
    vocab = {t: c for t, c in counter.items() if c >= min_freq}
    CACHE.mkdir(parents=True, exist_ok=True)
    with gzip.open(VOCAB, "wt", encoding="utf-8") as fh:
        for t in sorted(vocab):
            fh.write(f"{t}\t{vocab[t]}\n")
    print(f"[✓] المعجم: {len(vocab):,} كلمة (من {len(files):,} صفحة مفهرسة) → {VOCAB.relative_to(ROOT)}")
    return vocab


def load_vocab() -> dict[str, int]:
    if not VOCAB.exists():
        return build_vocab()
    out: dict[str, int] = {}
    with gzip.open(VOCAB, "rt", encoding="utf-8") as fh:
        for ln in fh:
            parts = ln.rstrip("\n").split("\t")
            if not parts or not parts[0]:
                continue
            out[parts[0]] = int(parts[1]) if len(parts) > 1 else 1
    return out


# ------------------------------------------------------------------ الإصلاح
def repair(text: str) -> tuple[str, dict]:
    """يطبّق الإصلاحات الحتمية ويعيد (النص، الإحصاءات)."""
    stats = {"presentation": len(PRESENTATION.findall(text))}
    if stats["presentation"]:
        text = unicodedata.normalize("NFKC", text)
    stats["spaced_marks"] = len(SPACED_MARK.findall(text))
    text = SPACED_MARK.sub(r"\1", text)
    stats["lam_alef"] = len(LAM_ALEF_BAD.findall(text))
    text = LAM_ALEF_BAD.sub(r"\1\3\2", text)
    stats["tabs"] = len(TAB.findall(text))
    return text, stats


def evaluate_page(raw: str, vocab: set[str]) -> dict:
    """يقيس صفحة واحدة: نسبة الكلمات الصحيحة + العيوب."""
    text, stats = repair(raw)
    norm = normalize(text)
    tokens = [t for t in norm.split() if len(t) >= 3 and len(LETTER.findall(t)) >= 3]
    valid = sum(1 for t in tokens if t in vocab)
    rate = valid / len(tokens) if tokens else 0.0
    letters = len(LETTER.findall(text))
    if letters < 40:
        verdict = "فارغة"
    elif not tokens:
        verdict = "مشوَّهة"
    elif rate >= 0.90:
        verdict = "سليمة"
    elif rate >= 0.75:
        verdict = "مقبولة"
    else:
        verdict = "مشوَّهة"
    return {
        "letters": letters,
        "tokens": len(tokens),
        "valid": valid,
        "rate": rate,
        "verdict": verdict,
        **stats,
    }


def parse_pages(spec: str, total: int) -> list[int]:
    if spec == "all":
        return list(range(1, total + 1))
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return sorted(p for p in out if 1 <= p <= total)


def audit_pdf(pdf: Path, pages_spec: str, vocab: set[str]) -> dict:
    doc = pymupdf.open(str(pdf))
    total = doc.page_count
    pages = parse_pages(pages_spec, total)
    rows = {}
    for p in pages:
        rows[p] = evaluate_page(doc[p - 1].get_text("text"), vocab)
    doc.close()

    counts = Counter(r["verdict"] for r in rows.values())
    rates = [r["rate"] for r in (rows[p] for p in pages) if r["tokens"]]
    overall = sum(r["valid"] for r in rows.values()) / max(1, sum(r["tokens"] for r in rows.values()))
    summary = {
        "file": pdf.name,
        "page_count": total,
        "audited": len(pages),
        "validity": round(overall, 4),
        "median": round(sorted(rates)[len(rates) // 2], 4) if rates else 0,
        "min": round(min(rates), 4) if rates else 0,
        "clean": counts.get("سليمة", 0),
        "acceptable": counts.get("مقبولة", 0),
        "garbled": counts.get("مشوَّهة", 0),
        "empty": counts.get("فارغة", 0),
        "verdict": "نصّي" if overall >= 0.90 else ("هجين" if overall >= 0.75 else "بصري"),
    }

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# تدقيق جودة النص — {pdf.name}",
        "",
        f"- **الصفحات:** {total} | **المدقَّقة:** {len(pages)}",
        f"- **نسبة الكلمات الصحيحة:** {overall:.2%} | الوسيط {summary['median']:.2%} | الأدنى {summary['min']:.2%}",
        f"- **الحكم:** {summary['verdict']}",
        f"- **التوزيع:** سليمة {summary['clean']} | مقبولة {summary['acceptable']} | مشوَّهة {summary['garbled']} | فارغة {summary['empty']}",
        "",
        "| صفحة | حروف | كلمات | صحيحة | النسبة | الحكم | أشكال عرض | حركات منفصلة | لام-ألف |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in pages:
        r = rows[p]
        lines.append(
            f"| {p} | {r['letters']} | {r['tokens']} | {r['valid']} | {r['rate']:.1%} | {r['verdict']} | "
            f"{r['presentation']} | {r['spaced_marks']} | {r['lam_alef']} |"
        )
    bad = [p for p in pages if rows[p]["verdict"] == "مشوَّهة"]
    if bad:
        lines += ["", f"**صفحات تحتاج تحويلًا بصريًا ({len(bad)}):** " + ", ".join(map(str, bad[:200]))]
    (LOG_DIR / f"audit_{pdf.stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary["worst"] = sorted((p for p in pages if rows[p]["tokens"]), key=lambda p: rows[p]["rate"])[:10]
    summary["bad_pages"] = bad
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="تدقيق جودة النص المستخرج من PDF")
    ap.add_argument("--build-vocab", action="store_true", help="بناء معجم المراجع فقط")
    ap.add_argument("--pdf", action="append", default=[], help="مسار PDF (يتكرر)")
    ap.add_argument("--pages", default="all", help="all أو 1-20 أو 5,9,30")
    ap.add_argument("--min-freq", type=int, default=2, help="أقل تكرار لكلمة في المعجم")
    args = ap.parse_args()

    vocab = build_vocab(args.min_freq) if args.build_vocab else load_vocab()
    if not vocab:
        print("[!] لا معجم. شغّل --build-vocab أولًا.")
        return 2
    print(f"[*] المعجم: {len(vocab):,} كلمة")
    if not args.pdf:
        return 0

    results = []
    for p in args.pdf:
        pdf = Path(p)
        if not pdf.is_absolute():
            pdf = ROOT / p
        if not pdf.is_file():
            print(f"[!] لا يوجد: {pdf}")
            return 2
        s = audit_pdf(pdf, args.pages, vocab)
        results.append(s)
        print(f"[{s['verdict']}] {s['file']}: {s['validity']:.2%} صحيحة | "
              f"سليمة {s['clean']} · مقبولة {s['acceptable']} · مشوَّهة {s['garbled']} · فارغة {s['empty']}")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out = LOG_DIR / "audit_summary.json"
    prev = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    for s in results:
        prev[s["file"]] = s
    out.write_text(json.dumps(prev, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[*] الملخّص: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
