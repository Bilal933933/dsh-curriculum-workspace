#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sarf_mizan.py — الميزان الصرفي وخطوات الإعلال بلفظ الصرفيين.

الغرض:
    يغلّف محرّك `sarf_ilal.py` المستورد (scripts/vendor/arabiyya/) في أمر سطر
    أوامر، ليعطي الوزن الأصلي والصورة الأصلية وخطوات الإعلال والإبدال والإدغام
    حتى الصورة المنطوقة، مع الوزن على لفظ الكلمة. يعمل بلا شبكة وبلا أي مكتبة
    خارجية، ويصلح لمسائل الصرف التي يخطئ فيها النموذج حين يجيب من حفظه.

طرقا العمل:
    1) صريح: الوزن والجذر معروفان (دقة كاملة، هو المسار الذي تختبره الحالات
       المعيارية) — مثل «مِفْعَال من الوعد».
    2) ترشيحي: الكلمة وحدها؛ يُرشَّح الجذر بمطابقة القوالب حرفًا بحرف ثم لا
       يُقبل إلا ما أعاد الكلمة نفسها. المرشحات حَسب، والتفريق بين واوي ويائي
       يحتاج معجمًا (index/ أو shamela_client.py).

ما يقرأه:
    scripts/vendor/arabiyya/sarf_ilal.py فقط. لا شبكة، ولا ملفات منهج.

ما يكتبه:
    لا شيء.

الاستخدام:
    # بجذر معروف (أدقّ مسار، وهو الذي تختبره الحالات المعيارية):
    python scripts/retrieval/sarf_mizan.py "اِتَّصَلَ" --root وصل
    python scripts/retrieval/sarf_mizan.py "اسْتِقَامَة" --root قوم
    # بوزن وجذر معًا:
    python scripts/retrieval/sarf_mizan.py "مِيزَان" --wazn مِفْعَال --root وزن
    # بلا جذر: ترشيح من الحروف، وينجح فيما لم يتغيّر وضعه بالإعلال:
    python scripts/retrieval/sarf_mizan.py "يَبِيعُ" --pos verb
    # عدة كلمات بمخرجات JSON للنقل إلى ورقة الدرس:
    python scripts/retrieval/sarf_mizan.py "مَدْعُوّ" "داعٍ" --root دعو --json

تنبيه منهجي:
    حكم المحرّك قياسي على القوالب المدرجة، ولا يبلغ الأوزان الشاذة والرباعي
    والمعرب والجامد. إن عارض المقرر في كتاب الطالب فالمقرر هو المتقدِّم،
    ويُنبَّه الطالب على الخلاف لا يُسلَّم به.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE = Path(__file__).resolve().parents[2]
VENDOR = WORKSPACE / "scripts" / "vendor" / "arabiyya"
sys.path.insert(0, str(VENDOR))
import sarf_ilal as I  # noqa: E402

HARAKAT = I.FATHA + I.DAMMA + I.KASRA + I.SUKUN

TEMPLATES = {}
for wazn, desc, form in I.VERB_TEMPLATES:
    TEMPLATES.setdefault(wazn, (desc, form, "verb"))
for wazn, desc, form in I.NOUN_TEMPLATES:
    TEMPLATES.setdefault(wazn, (desc, form, "noun"))


def from_template(word: str, wazn: str, root: str, pos: str) -> dict:
    """المسار الصريح: وزن معروف وجذر معروف."""
    desc, form, tpl_pos = TEMPLATES.get(wazn, ("وزن خارج القوالب المدرجة، حُسب على الميزان المدخل", "I", pos))
    tpl = I.parse_wazn(wazn)
    if tpl is None:
        raise ValueError(f"تعذّر تحليل الوزن «{wazn}»")
    ctx = I.ctx_for(wazn, tpl_pos, form)
    result = I.derive(tpl, root, ctx)
    if result is None:
        raise ValueError(f"لا يحتمل الوزن «{wazn}» الجذرَ «{root}»")
    asl, surf, steps = result
    return {
        "الكلمة": word, "الجذر": " ".join(root), "نوع الجذر": I.root_type(root),
        "الصيغة": desc, "الوزن": wazn, "الأصل": asl,
        "خطوات الإعلال": [{"النوع": s["النوع"], "الخطوة": s["الخطوة"], "فصار": s["الصورة"]} for s in steps] or "لا إعلال فيه",
        "الوزن على لفظه": I.surface_wazn(tpl, root, ctx),
        "مطابق للمكتوبة": I.bare(surf) == I.bare(word),
    }


def from_candidates(word: str, roots: list[str], pos: str | None, limit: int) -> list[dict]:
    """قوالب مطابقة للكلمة؛ بجذر معلوم يكتفي به، وبغيره يرشَّح من حروف الكلمة.

    الترشيح بالحروف لا يستعيد جذرًا غيّره الإعلال (اِتَّصَلَ من «و ص ل»،
    اسْتِقَامَة بألف عوضًا عن عين «ق و م»)؛ فهناك يُمرَّر --root.
    """
    al_prefix = False
    given = list(roots)
    if not roots:
        roots = I.skeleton_roots(word, pos, 0 if any(c in HARAKAT for c in word) else 2)
    matches = I.match_word(word, roots, pos)
    if not matches and I.bare(word).startswith("ال") and len(I.bare(word)) > 4:
        stem = word[2:]
        al_prefix = True
        matches = I.match_word(stem, given or I.skeleton_roots(stem, pos, 0), pos)
    seen, out = set(), []
    for m in sorted(matches, key=lambda x: x["order"]):
        key = (m["root"], m["wazn"])
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "الكلمة": m["surf"], "الجذر": " ".join(m["root"]), "نوع الجذر": I.root_type(m["root"]),
            "الصيغة": m["desc"], "الوزن": m["wazn"], "الأصل": m["asl"],
            "خطوات الإعلال": [{"النوع": s["النوع"], "الخطوة": s["الخطوة"], "فصار": s["الصورة"]} for s in m["steps"]] or "لا إعلال فيه",
            "الوزن على لفظه": m["swazn"],
            "تنبيه": ("الميزان محسوب بعد حذف لام التعريف، فهي زائدة لا تدخل في الوزن"
                      if al_prefix else None),
        })
        if len(out) >= limit:
            break
    return out


def print_report(word: str, readings: list[dict], note: str | None) -> None:
    if not readings:
        print(f"«{word}» — لا يقابلها قالب مدرج؛ قد تكون رباعية أو معرّبة أو جامدة "
              f"أو على وزن غير قياسي.")
        return
    for i, r in enumerate(readings, 1):
        head = f"«{word}» ← {r['الوزن']}" if len(readings) == 1 else f"[{i}] «{word}» ← {r['الوزن']}"
        print(f"\n{head}  ({r['الجذر']} · {r['نوع الجذر']})")
        print(f"  الصيغة: {r['الصيغة']}")
        print(f"  الأصل:  {r['الأصل']}")
        steps = r["خطوات الإعلال"]
        if isinstance(steps, str):
            print(f"  الإعلال: {steps}")
        else:
            for j, s in enumerate(steps, 1):
                print(f"  {j}. [{s['النوع']}] {s['الخطوة']} → {s['فصار']}")
        print(f"  المنطوقة: {r['الكلمة']}   ·   الوزن على لفظه: {r['الوزن على لفظه']}")
        if r.get("تنبيه"):
            print(f"  تنبيه: {r['تنبيه']}")
    if note:
        print(f"\n  ملاحظة: {note}")


def main() -> int:
    ap = argparse.ArgumentParser(description="الميزان الصرفي وخطوات الإعلال (محرّك قياسي محلي).")
    ap.add_argument("words", nargs="+", help="الكلمة، ويُستحسن ضبطها بالحركات")
    ap.add_argument("--wazn", help="الوزن صريحًا (يحتاج --root معه)")
    ap.add_argument("--root", help="الجذر صريحًا: مفصول «و ص ل» أو موصولًا «وصل»")
    ap.add_argument("--pos", choices=["verb", "noun"], help="تقييد الترشيح بفعل أو باسم")
    ap.add_argument("--limit", type=int, default=3, help="أقصى عدد قراءات للكلمة (افتراضي 3)")
    ap.add_argument("--json", action="store_true", help="مخرجات JSON بدل العرض المقرَّب")
    ns = ap.parse_args()

    root = ns.root.replace(" ", "") if ns.root else None
    if ns.wazn and not root:
        print("[!] --wazn يحتاج --root معه", file=sys.stderr)
        return 2
    if ns.wazn and len(ns.words) > 1:
        print("[!] المسار الصريح (وزن+جذر) لكلمة واحدة", file=sys.stderr)
        return 2

    results = {}
    for word in ns.words:
        if ns.wazn:
            pos = ns.pos or TEMPLATES.get(ns.wazn, ("", "", "noun"))[2]
            try:
                readings = [from_template(word, ns.wazn, root, pos)]
            except ValueError as exc:
                print(f"[!] {exc}", file=sys.stderr)
                return 1
            note = None
        else:
            readings = from_candidates(word, [root] if root else [], ns.pos, ns.limit)
            notes = []
            if len(readings) > 1:
                notes.append("قراءات محتملة؛ الراجح منها بما يدل عليه السياق أو المعجم "
                             "(index/ أو scripts/retrieval/shamela_client.py)")
            if not root:
                notes.append("الجذر مرشَّح من حروف الكلمة، فلا يستعيد ما غيّره الإعلال؛ "
                             "إن لم تُصب فمرِّر --root (مثل: --root وصل)")
            elif not readings:
                notes.append(f"لا قالب مدرجًا يطابق «{word}» من «{root}»؛ راجع الضبط أو الجذر")
            note = " · ".join(notes) or None
        results[word] = {"القراءات": readings, "ملاحظة": note}

    if ns.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for word, block in results.items():
            print_report(word, block["القراءات"], block["ملاحظة"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
