#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plans_inventory.py — بناء سجل توزيعات المناهج `meta/plans.yaml`.

الغرض:
    جرد مصادر التوزيعات داخل `plans_src/` (صور رسمية + PDF) وتحويلها إلى وحدات
    موحّدة قابلة للتفريغ، مع الحفاظ على حالة كل وحدة عند إعادة التشغيل (idempotent).

المصادر:
    plans_src/tawzee/<مجلد>/            صور توزيعات رسمية مختومة (وحدة = مجلد)
    plans_src/tawzee/_pdf-2027/*.pdf    PDF رسمي
    plans_src/pdf/<مرحلة>/<صف>/*.pdf    PDF مستخرج (أضواء)

الاستخدام:
    python scripts/convert/plans_inventory.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pymupdf
import yaml

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "plans_src"
REGISTRY = ROOT / "meta" / "plans.yaml"
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}

# عنوان كل مجلد صور — مأخوذ من فهرس المصدر (00-INDEX.md)، لا اجتهاد.
TW_TITLES = {
    "01-sanaya-idadi": "توزيع منهج مهارات الصناعة — المرحلة الإعدادية",
    "02-drasat-ibtidai": "توزيع منهج الدراسات الاجتماعية — المرحلة الابتدائية (ت1)",
    "03-drasat-idadi": "توزيع منهج الدراسات الاجتماعية — المرحلة الإعدادية",
    "04-tech-idadi": "توزيع منهج تكنولوجيا المعلومات والاتصالات — المرحلة الإعدادية (ت1+ت2)",
    "05-programming-sec1": "توزيع منهج البرمجة والمنصة — الصف الأول الثانوي (ت1+ت2)",
    "06-tech-ibtidai": "توزيع منهج تكنولوجيا المعلومات والاتصالات — المرحلة الابتدائية (ت1+ت2)",
    "07-din-masihi": "توزيع منهج التربية الدينية المسيحية — كل المراحل",
    "08-din-idadi": "توزيع منهج التربية الدينية — المرحلة الإعدادية",
    "09-din-islami": "توزيع منهج التربية الدينية الإسلامية — كل المراحل",
    "10-math-ibtidai": "توزيع منهج الرياضيات — المرحلة الابتدائية",
    "11-math-idadi": "توزيع منهج الرياضيات — المرحلة الإعدادية",
    "12-science": "توزيع منهج العلوم — المرحلتان الابتدائية والإعدادية",
    "13-math-sec": "توزيع منهج الرياضيات — المرحلة الثانوية",
    "14-math-all": "توزيع منهج الرياضيات — المراحل الثلاث",
    "15-pe-ibtidai-idadi": "توزيع منهج التربية الرياضية — المرحلتان الابتدائية والإعدادية",
    "17-arabic-all": "توزيع منهج اللغة العربية — المراحل الثلاث (ت1)",
    "18-english": "توزيع منهج اللغة الإنجليزية — كل الصفوف",
    "19-french": "توزيع منهج اللغة الفرنسية",
    "20-computer-qureo": "توزيع منهج الحاسب والبرمجة (Qureo)",
    "23-science-integrated-sec1": "خريطة منهج العلوم المتكاملة — الصف الأول الثانوي",
    "24-art-vision-message": "التربية الفنية — رؤية ورسالة المادة (ليست توزيعًا)",
    "25-music-2027": "توزيع منهج التربية الموسيقية — المراحل الثلاث",
    "26-industry-2027": "توزيع منهج مهارات الصناعة — الابتدائي (4/5/6)",
    "27-statistics-sec3-2027": "توزيع منهج الإحصاء (أدبي) — الصف الثالث الثانوي",
    "28-agriculture-primary-2027": "توزيع منهج مهارات الزراعة — الابتدائي (4/5/6)",
    "29-agriculture-prep-2027": "توزيع منهج مهارات الزراعة — الإعدادي (1/2/3)",
    "30-science-primary-prep-2027": "Science Curriculum Plan — الابتدائي والإعدادي",
    "31-english-2027-pergrade": "توزيع منهج اللغة الإنجليزية — 11 صفًا (رسمي مختوم)",
    "32-math-sec2-sec3-2027": "توزيع منهج الرياضيات — ثانية وثالثة ثانوي",
}

SUBJ_EN = {
    "اللغة العربية": "arabic",
    "الرياضيات": "math",
    "العلوم": "science",
    "الدراسات الاجتماعية": "studies",
    "التربية الدينية": "religion",
    "اللغة الإنجليزية": "english",
    "اللغة الفرنسية": "french",
    "اللغة الألمانية": "german",
    "اللغة الإيطالية": "italian",
    "الأحياء": "biology",
    "التاريخ": "history",
    "الفيزياء": "physics",
    "الكيمياء": "chemistry",
    "الجغرافيا": "geography",
    "غير محدد": "unknown",
}

STAGE_CODE = {"رياض الأطفال": "kg", "الابتدائية": "p", "الإعدادية": "prep", "الثانوي العام": "sec"}
GRADE_NUM = {"الأول": 1, "الثاني": 2, "الثالث": 3, "الرابع": 4, "الخامس": 5, "السادس": 6,
             "أول": 1, "ثان": 2}


def slug(text: str) -> str:
    """اسم مجلد مخرجات آمن من عنوان عربي."""
    s = re.sub(r"[\\/:*?\"<>|]", "", text)
    s = re.sub(r"[\s،,]+", "_", s.strip())
    return re.sub(r"_+", "_", s).strip("_")


def load_existing() -> dict[str, dict]:
    if not REGISTRY.exists():
        return {}
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    return {u["id"]: u for u in data.get("units", [])}


def image_units(existing: dict[str, dict]) -> list[dict]:
    out = []
    for folder in sorted((SRC / "tawzee").iterdir()):
        if not folder.is_dir() or folder.name == "_pdf-2027":
            continue
        imgs = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMG_EXT)
        if not imgs:
            continue
        uid = "plan_tw_" + folder.name.replace("-", "_")
        title = TW_TITLES.get(folder.name, folder.name)
        prev = existing.get(uid, {})
        dir_title = title if title.startswith(("توزيع", "خطة", "خريطة", "Science", "التربية")) \
            else "توزيع_" + title
        out.append({
            "id": uid,
            "title": title,
            "authority": "official",
            "kind": "images",
            "source": folder.relative_to(ROOT).as_posix(),
            "text_dir": prev.get("text_dir") or slug(dir_title),
            "pages": len(imgs),
            "status": prev.get("status", "pending"),
            "pages_converted": prev.get("pages_converted", 0),
        })
    return out


def pdf_units(existing: dict[str, dict]) -> list[dict]:
    out = []
    for pdf in sorted((SRC / "tawzee" / "_pdf-2027").glob("*.pdf")):
        doc = pymupdf.open(pdf)
        uid = "plan_tw_" + pdf.stem.replace("-", "_")
        prev = existing.get(uid, {})
        title = "توزيع منهج اللغة العربية — جميع المراحل (ت1)" if "arabic" in pdf.stem \
            else "خطة توزيع منهج التربية الفنية — المرحلة الابتدائية"
        out.append({
            "id": uid,
            "title": title,
            "authority": "official",
            "kind": "pdf",
            "source": pdf.relative_to(ROOT).as_posix(),
            "text_dir": prev.get("text_dir") or slug("توزيع_" + title),
            "pages": doc.page_count,
            "status": "broken" if doc.page_count == 0 else prev.get("status", "pending"),
            "pages_converted": prev.get("pages_converted", 0),
        })

    for pdf in sorted((SRC / "pdf").rglob("*.pdf")):
        stage_ar = pdf.relative_to(SRC / "pdf").parts[0]
        grade_ar = pdf.parent.name
        subject_ar = pdf.stem
        stage = STAGE_CODE.get(stage_ar, "?")
        m = re.search(r"الصف (\S+)", grade_ar)
        grade = GRADE_NUM.get(m.group(1), 0) if m else GRADE_NUM.get(grade_ar.split()[1], 0)
        subj = SUBJ_EN.get(subject_ar, "unknown")
        uid = f"plan_{stage}{grade}_{subj}"
        prev = existing.get(uid, {})
        doc = pymupdf.open(pdf)
        out.append({
            "id": uid,
            "title": f"توزيع منهج {subject_ar} — {grade_ar}" if stage_ar != "رياض الأطفال"
                     else f"توزيع منهج {subject_ar} — {grade_ar} (رياض الأطفال)",
            "authority": "derived",
            "kind": "pdf",
            "source": pdf.relative_to(ROOT).as_posix(),
            "text_dir": prev.get("text_dir") or slug(f"توزيع_{subject_ar}_{grade_ar}"),
            "stage": stage,
            "grade": grade,
            "subject": subj,
            "pages": doc.page_count,
            "status": "broken" if doc.page_count == 0 else prev.get("status", "pending"),
            "pages_converted": prev.get("pages_converted", 0),
        })
    return out


def main() -> int:
    existing = load_existing()
    units = image_units(existing) + pdf_units(existing)
    ids = [u["id"] for u in units]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        print("✗ معرّفات مكررة:", sorted(dup))
        return 1
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(
        yaml.safe_dump({"version": 1, "units": units}, allow_unicode=True,
                       sort_keys=False, width=200),
        encoding="utf-8")
    print(f"[✓] {REGISTRY.relative_to(ROOT)}: {len(units)} وحدة | "
          f"{sum(u['pages'] for u in units)} صفحة")
    print("   رسمي:", sum(1 for u in units if u["authority"] == "official"),
          "| مستخرج:", sum(1 for u in units if u["authority"] == "derived"),
          "| تالف:", sum(1 for u in units if u["status"] == "broken"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
