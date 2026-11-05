#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مراجعة مخرجات الطبقة النصية (Text-Layer Review) — رخيصة وبلا صور
=================================================================
الغرض:
    مراجعة ملفات `output/<book>/page_XXX.md` الناتجة عن `pdf_text_extract.py`
    على مرحلتين: فحص آلي مجاني، ثم (اختياريًا) إصلاح بنموذج نصي فقط.

    الفارق الجوهري عن `review_batch.py`: هنا **لا تُرسل صورة الصفحة**،
    فالتكلفة تنخفض إلى نحو 1/1000 من تكلفة المراجعة البصرية.

المميزات:
    - `--flags-only` : فحص آلي بلا أي استدعاء API (الافتراضي).
    - `--llm`        : إصلاح الصفحات المشبوهة بنموذج نصي (بلا صور).
    - إصلاحات نصية فقط: ترتيب مقلوب، مسافات، حروف منفصلة، أسطر مكررة.
      لا يُعاد كتابة المحتوى ولا تُضاف معلومات.

الملفات التي يقرأها:
    - .env (GEMINI_OCR_KEYS, GEMINI_REVIEW_MODEL)
    - output/<book>/page_XXX.md

الملفات التي يكتبها:
    - output/<book>/page_XXX.md                (فقط مع --llm وعند وجود تغيير)
    - logs/chapters/<book>/text_review_log.md  (تقرير المراجعة)

الاستخدام:
    python scripts/review_text_batch.py --book <book> --start 1 --end 154 --flags-only
    python scripts/review_text_batch.py --book <book> --start 1 --end 154 --llm
"""

import argparse
import difflib
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lib.gemini_client import generate, load_env, QuotaRing  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROMPT = """أنت مدقّق نص عربي مستخرج آليًا من PDF (بلا صورة).
أصلح فقط أخطاء الاستخراج الآلي:
1. ترتيب الكلمات أو الحروف المقلوب.
2. المسافات الزائدة/الناقصة، والكلمات المقطوعة بين سطرين.
3. الحروف المنفصلة أو المكررة بلا سبب، ومحارف التحكم.
4. أسطر التكرار الناتجة عن خطأ استخراج (احتفظ بسطر واحد).

القواعد الصارمة:
- لا تضف كلمة أو جملة أو شرحًا غير موجود.
- لا تغيّر المحتوى ولا الأسلوب ولا التشكيل إن كان صحيحًا.
- الجداول تُبقى جداول Markdown.
- أخرج Markdown فقط بلا أي مقدمة.
"""

_CTRL = re.compile("[\u200b\u200c\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_LETTER = re.compile("[\u0621-\u064a]")
_DIACRITIC = re.compile("[\u064b-\u0652\u0670]")
_NOSPACE = re.compile(r"[\u0600-\u06ff]\S{40,}")


def flags(text: str) -> list[str]:
    """علامات شبهة نصية (بلا نموذج)."""
    fs = []
    t = text.strip()
    if len(_LETTER.findall(t)) < 40:
        fs.append("نص قصير")
    if _CTRL.search(t):
        fs.append("محارف تحكم")
    if _NOSPACE.search(t):
        fs.append("بلا مسافات")
    lines = [ln for ln in t.splitlines() if ln.strip()]
    if len(lines) >= 8 and len(set(lines)) < len(lines) * 0.6:
        fs.append("أسطر مكررة")
    letters = len(_LETTER.findall(t))
    diacritics = len(_DIACRITIC.findall(t))
    if letters > 80 and diacritics < letters * 0.02:
        fs.append("تشكيل ناقص")
    if t.count("|") and "---" not in t:
        if len([ln for ln in t.splitlines() if "|" in ln]) >= 2:
            fs.append("جدول مفكوك")
    return fs


def load_settings():
    env = load_env(ROOT / ".env")
    keys = [k.strip() for k in env.get("GEMINI_OCR_KEYS", "").split(",") if k.strip()]
    if not keys:
        sys.exit("خطأ: لا توجد مفاتيح في GEMINI_OCR_KEYS داخل .env")
    model = env.get("GEMINI_REVIEW_MODEL", "gemini-3.5-flash").strip()
    fallback = env.get("GEMINI_REVIEW_FALLBACK", "").strip()
    models = [model] + ([fallback] if fallback and fallback != model else [])
    return keys, models


def call_fix(ring, text: str, timeout: int = 60):
    """إصلاح صفحة واحدة بنداء نصي فقط. يعيد (نص مصحح, خطأ)."""
    parts = [
        {"text": PROMPT},
        {"text": f"النص:\n\n{text}"},
    ]
    out, _model, _usage, err = generate(ring, parts, timeout=timeout, temperature=0.0)
    if err:
        return None, err
    if out.startswith("```"):
        out = re.sub(r"^```[a-z]*\n|\n```$", "", out).strip()
    return out, None


def main() -> int:
    ap = argparse.ArgumentParser(description="مراجعة نصية رخيصة لمخرجات الطبقة النصية")
    ap.add_argument("--book", required=True)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=0)
    ap.add_argument("--flags-only", action="store_true", help="فحص آلي فقط بلا API (الافتراضي)")
    ap.add_argument("--llm", action="store_true", help="إصلاح المشبوه بنموذج نصي بلا صور")
    ap.add_argument("--all", action="store_true", help="طبّق --llm على كل الصفحات")
    args = ap.parse_args()

    out_dir = ROOT / "output" / args.book
    log_dir = ROOT / "logs" / "chapters" / args.book
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "text_review_log.md"

    files = sorted(out_dir.glob("page_*.md"))
    pages = [f for f in files
             if args.start <= int(f.stem.split("_")[1]) <= (args.end or 10**6)]
    if not pages:
        print("[!] لا توجد صفحات في هذا المدى")
        return 1

    suspect = []
    for f in pages:
        fs = flags(f.read_text(encoding="utf-8"))
        if fs:
            suspect.append((f, fs))

    print(f"[*] {args.book} | صفحات {len(pages)} | مشبوهة {len(suspect)}")
    for f, fs in suspect[:10]:
        print(f"    - {f.name}: {', '.join(fs)}")
    if len(suspect) > 10:
        print(f"    ... و{len(suspect) - 10} صفحة أخرى")

    if not args.llm:
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\n## فحص آلي {args.start}–{args.end or 'النهاية'} — {time.strftime('%Y-%m-%d %H:%M')}\n")
            log.write(f"- صفحات: {len(pages)} | مشبوهة: {len(suspect)}\n")
            for f, fs in suspect:
                log.write(f"- {f.name}: {', '.join(fs)}\n")
        print(f"[✓] التقرير: {log_path.relative_to(ROOT)}")
        return 0

    # ------------------------------------------------------------ إصلاح نصي
    keys, models = load_settings()
    ring = QuotaRing(keys, models)
    targets = [(f, fs) for f, fs in pages] if args.all else suspect
    targets = [(f, flags(f.read_text(encoding="utf-8"))) for f, _ in [(f, None) for f, _ in targets]]

    fixed = same = failed = 0
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n## إصلاح نصي {args.start}–{args.end or 'النهاية'} — {time.strftime('%Y-%m-%d %H:%M')}\n")
        log.write(f"- مستهدف: {len(targets)} صفحة\n")
        for f, fs in targets:
            text = f.read_text(encoding="utf-8")
            corrected, err = call_fix(ring, text)
            if err:
                failed += 1
                print(f"[✗] {f.name}: {err}")
                log.write(f"- {f.name}: فشل ({err})\n")
                continue
            if not corrected or len(_LETTER.findall(corrected)) < 20:
                same += 1
                continue
            ratio = difflib.SequenceMatcher(None, text, corrected).ratio()
            if ratio < 0.999:
                f.write_text(corrected.rstrip() + "\n", encoding="utf-8")
                fixed += 1
                log.write(f"- {f.name}: صُحّح (تشابه {ratio:.3f})\n")
                print(f"[✓] {f.name}: تشابه {ratio:.3f}")
            else:
                same += 1
                log.write(f"- {f.name}: مطابق\n")
            time.sleep(0.3)
        log.write(f"\n**الملخص:** مصحّح {fixed} | مطابق {same} | فشل {failed}.\n")

    print(f"[*] انتهى: مصحّح {fixed} | مطابق {same} | فشل {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
