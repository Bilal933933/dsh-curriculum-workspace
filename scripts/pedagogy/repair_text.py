#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
repair_text.py — إصلاح حتمي لنص PDF العربي بقيادة المعجم.
==========================================================
المشكلة:
    بعض ملفات PDF العربية تُخرج الحروف بترميز خطّ قديم، فتقلب حرفين
    متجاورين (`تقدمي` = تقديم)، أو تُبدل حرفًا (`البياف` = البيان)، أو
    تُخرج محارف لاتينية مكان لِغاءات عربية (`ē` = ته). النص يبقى مقروءًا
    للعين لكنه غير قابل للمطابقة المعجمية.

الحل:
    إصلاح على ثلاث مراحل، كلها حتمية ومُحصاة:
    R0  NFKC + إزالة محارف الحشو.
    R1  قواعد صيغية: حركة منفصلة · انقلاب لام-ألف · لِغاءات مستبدلة.
    R2  إصلاح بقيادة المعجم: كل كلمة غير موجودة في معجم المستودع يُولَّد
        لها مرشّحون بمسافة تحرير ≤ 2 (تبديل متجاور · إبدال حرف · حذف حرف)،
        ويُقبل المرشّح الوحيد الموجود في المعجم فقط. أي التباس ⇒ لا تغيير.

    كل تغيير يُسجَّل: (قبل ← بعد، العملية). ولا يُقبل مرشّح غير موجود في
    المعجم، فلا يُختلق نص جديد.

الاستخدام:
    python scripts/pedagogy/repair_text.py --probe --pdf X.pdf --pages 1-20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "retrieval"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_index import normalize  # noqa: E402
import audit_text_quality as A  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

LETTER = re.compile(r"[\u0621-\u064a]")
ARABIC = "ابتثجحخدذرزسشصضطظعغفقكلمنهويىءأإآؤئة"
STRAY = re.compile("[\u0590-\u05ff\u0100-\u017f]")  # عبري + لاتيني ممتد (لِغاءات معطوبة)
SPACED_MARK = re.compile(r"[ \t]+([\u064b-\u0652\u0670])")
LAM_ALEF_BAD = re.compile("([\u0627])([\u0622\u0623\u0625])([\u0644])")
# لِغاءات معطوبة رصدناها بالقياس (تكرار + سياق)
GLYPH_MAP = {"ē": "ته", "Ĕ": "نه"}

# أولوية العمليات عند تساوي التكرار: الأبسط أولًا.
_OP_RANK = {"swap1": 0, "swap2": 1, "sub1": 2, "del1": 3, "del1sub1": 4}


def stage1(text: str) -> tuple[str, Counter]:
    """إصلاح صيغي حتمي بلا معجم."""
    st: Counter = Counter()
    if A.PRESENTATION.search(text):
        st["nfkc"] = len(A.PRESENTATION.findall(text))
        text = unicodedata.normalize("NFKC", text)
    for k, v in GLYPH_MAP.items():
        if k in text:
            st[f"glyph:{k}"] = text.count(k)
            text = text.replace(k, v)
    if STRAY.search(text):
        st["stray"] = len(STRAY.findall(text))
        text = STRAY.sub("", text)
    hits = len(SPACED_MARK.findall(text))
    if hits:
        st["spaced_marks"] = hits
        text = SPACED_MARK.sub(r"\1", text)
    hits = len(LAM_ALEF_BAD.findall(text))
    if hits:
        st["lam_alef"] = hits
        text = LAM_ALEF_BAD.sub(r"\1\3\2", text)
    return text, st


def _candidates(tok: str):
    """مرشّحات بمسافة تحرير ≤ 2، مرتّبة بالأولوية (تبديل ← إبدال ← حذف)."""
    n = len(tok)
    # 1) تبديل حرفين متجاورين
    for i in range(n - 1):
        yield "swap1", tok[:i] + tok[i + 1] + tok[i] + tok[i + 2:]
    # 2) تبديلان متباعدان (غالبًا لِغاءان مستقلان: "املعريف" ← "المعرفي")
    for i in range(n - 1):
        for j in range(i + 2, n - 1):
            c = list(tok)
            c[i], c[i + 1] = c[i + 1], c[i]
            c[j], c[j + 1] = c[j + 1], c[j]
            yield "swap2", "".join(c)
    # 3) إبدال حرف واحد
    for i, ch in enumerate(tok):
        for rep in ARABIC:
            if rep != ch:
                yield "sub1", tok[:i] + rep + tok[i + 1:]
    # 4) حذف حرف （حرف مكرر أو زائد)
    for i in range(n):
        yield "del1", tok[:i] + tok[i + 1:]
    # 5) حذف حرف وإبدال آخر
    for i in range(n):
        base = tok[:i] + tok[i + 1:]
        for k, ch in enumerate(base):
            for rep in ARABIC:
                if rep != ch:
                    yield "del1sub1", base[:k] + rep + base[k + 1:]


def repair_tokens(text: str, vocab: dict[str, int], min_freq: int = 20,
                  margin: float = 5.0) -> tuple[str, dict]:
    """يُصلح كلمات النص بقيادة المعجم مرتَّبًا بتكرار الكلمات.

    يُقبل المرشّح الأعلى تكرارًا فقط إذا كان تكراره ≥ `min_freq` ويفوق
    الثاني `margin` مرات. وإلا يُترك النص كما هو ويُعدّ ملتبسًا.
    """
    tokens = text.split()
    if not tokens:
        return text, {"tokens": 0, "bad": 0, "fixed": 0, "ambiguous": 0, "left": 0, "changes": []}

    bad_idx = []
    for i, tok in enumerate(tokens):
        core = normalize(tok)
        if len(core) < 3 or len(LETTER.findall(core)) < 3:
            continue
        if core not in vocab:
            bad_idx.append(i)

    fixed = ambiguous = 0
    changes = []
    for i in bad_idx:
        core = normalize(tokens[i])
        found: dict[str, tuple[int, str]] = {}
        for op, cand in _candidates(core):
            freq = vocab.get(cand)
            if not freq:
                continue
            prev = found.get(cand)
            if prev is None or _OP_RANK[op] < _OP_RANK[prev[1]]:
                found[cand] = (freq, op)
        if not found:
            continue
        ranked = sorted(found.items(), key=lambda kv: -kv[1][0])
        best_tok, (best_freq, best_op) = ranked[0]
        second = ranked[1][1][0] if len(ranked) > 1 else 0
        if best_freq >= min_freq and (second == 0 or best_freq >= margin * second):
            fixed += 1
            changes.append([core, best_tok, best_op, best_freq, second])
            tokens[i] = tokens[i].replace(core, best_tok, 1) if core in tokens[i] else best_tok
        else:
            ambiguous += 1

    left = len(bad_idx) - fixed - ambiguous
    stats = {
        "tokens": len(tokens),
        "bad": len(bad_idx),
        "fixed": fixed,
        "ambiguous": ambiguous,
        "left": left,
        "changes": changes,
    }
    return " ".join(tokens), stats


def repair(raw: str, vocab: dict[str, int]) -> tuple[str, dict]:
    """يُصلح النص كاملًا مع الحفاظ على فواصل الأسطر."""
    text, st1 = stage1(raw)
    out_lines = []
    agg: Counter = Counter()
    changes = []
    for line in text.splitlines():
        fixed_line, st = repair_tokens(line, vocab)
        out_lines.append(fixed_line)
        for k in ("tokens", "bad", "fixed", "ambiguous", "left"):
            agg[k] += st[k]
        changes.extend(st["changes"])
    stats = {**st1, **{k: agg[k] for k in ("tokens", "bad", "fixed", "ambiguous", "left")}}
    stats["changes"] = changes
    return "\n".join(out_lines), stats


# ------------------------------------------------------------------ CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="إصلاح نص PDF بقيادة المعجم (معاينة)")
    ap.add_argument("--pdf", action="append", required=True)
    ap.add_argument("--pages", default="1-10")
    ap.add_argument("--out", default="logs/pedagogy/repair_probe.json")
    args = ap.parse_args()

    vocab = A.load_vocab()
    if not vocab:
        print("[!] ابنِ المعجم أولًا: --build-vocab في audit_text_quality.py")
        return 2

    report = {}
    for p in args.pdf:
        pdf = Path(p)
        if not pdf.is_absolute():
            pdf = ROOT / p
        doc = pymupdf.open(str(pdf))
        pages = A.parse_pages(args.pages, doc.page_count)
        rows = []
        agg = Counter()
        for pg in pages:
            raw = doc[pg - 1].get_text("text")
            before = A.evaluate_page(raw, vocab)
            fixed_text, st = repair(raw, vocab)
            after = A.evaluate_page(fixed_text, vocab)  # بلا إصلاح ثانٍ: نص مُصلح
            rows.append({
                "page": pg,
                "before": round(before["rate"], 4),
                "after": round(after["rate"], 4),
                "before_verdict": before["verdict"],
                "after_verdict": after["verdict"],
                "bad": st.get("bad", 0),
                "fixed": st.get("fixed", 0),
                "ambiguous": st.get("ambiguous", 0),
                "left": st.get("left", 0),
                "stage1": {k: v for k, v in st.items() if k in
                           ("nfkc", "spaced_marks", "lam_alef", "stray") or k.startswith("glyph:")},
            })
            agg["bad"] += st.get("bad", 0)
            agg["fixed"] += st.get("fixed", 0)
            agg["ambiguous"] += st.get("ambiguous", 0)
            agg["left"] += st.get("left", 0)
        doc.close()
        avg_b = sum(r["before"] for r in rows) / len(rows)
        avg_a = sum(r["after"] for r in rows) / len(rows)
        report[pdf.name] = {
            "pages": len(rows),
            "before": round(avg_b, 4),
            "after": round(avg_a, 4),
            "agg": dict(agg),
            "rows": rows,
        }
        print(f"[✓] {pdf.name}: قبل {avg_b:.1%} ← بعد {avg_a:.1%} | "
              f"معطوبة {agg['bad']} | أُصلحت {agg['fixed']} | ملتبسة {agg['ambiguous']} | بقيت {agg['left']}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[*] {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
