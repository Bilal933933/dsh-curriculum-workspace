#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
فحص مستقل لملفات المرحلة الأولى (تنزيل الكتب) من archive.org.

لا يعدّل أي ملف؛ يقرأ المانيفست ويقارن الملفات الموجودة في _source بمعايير
القبول نفسها المستخدمة في download_one داخل adwaa_tawzee3.py:
  1) وجود الملف بالاسم المتوقع (slug)
  2) الحجم >= 99.5% من الحجم المعلن في archive.org
  3) الترويسة الأولية = %PDF-
  4) وجود %%EOF في آخر 2KB (كشف الاقتطاع)

الآن: workspace/manifest/adwaa_manifest.json
قراءة: _source/*.pdf (أول 5 بايت + آخر 2KB فقط)
الكتابة: workspace/logs/adwaa_verify_report.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adwaa_tawzee3 import load_manifest, slug, SRC_DIR, LOGS  # noqa: E402


def main():
    books = load_manifest()
    results = []
    for e in books:
        dest = SRC_DIR / (slug(e) + ".pdf")
        issues = []
        size = 0
        if not dest.exists():
            issues.append("مفقود")
        else:
            size = dest.stat().st_size
            if size < e["size"] * 0.995:
                issues.append(f"حجم ناقص ({size}/{e['size']})")
            with dest.open("rb") as fh:
                head = fh.read(5)
                fh.seek(max(0, size - 2048))
                tail = fh.read()
            if head != b"%PDF-":
                issues.append(f"ترويسة غير PDF ({head!r})")
            if b"%%EOF" not in tail[-2048:]:
                issues.append("لا يوجد %%EOF في الذيل")
        results.append({
            "grade": e["grade"], "subject": e["subject"], "id": e["id"],
            "file": dest.name, "ok": not issues, "size_local": size,
            "size_remote": e["size"], "issues": issues,
        })

    LOGS.mkdir(parents=True, exist_ok=True)
    out = LOGS / "adwaa_verify_report.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    bad = [r for r in results if not r["ok"]]
    total_gb = sum(r["size_local"] for r in results) / 2**30
    print(f"تم الفحص: {len(results) - len(bad)}/{len(results)} سليم — "
          f"{total_gb:.2f} GB — تقرير: {out}", flush=True)
    for r in bad:
        print(f"[مشكلة] {r['grade']} | {r['subject']} — {r['file']}", flush=True)
        for i in r["issues"]:
            print(f"    - {i}", flush=True)


if __name__ == "__main__":
    main()
