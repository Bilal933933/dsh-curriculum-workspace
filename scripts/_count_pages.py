import os
from pathlib import Path

import pymupdf

ROOT = Path(r"D:\المكتبة-التعليمية\01-كتب-مدرسية")
picks = {
    "prep1": [
        "الإعلام-التربوي", "التربية-الدينية-الإسلامية", "التربية-المسرحية",
        "الدراسات-الاجتماعية", "الرياضيات", "العلوم",
        "الكمبيوتر-وتكنولوجيا-المعلومات-والاتصالات", "المكتبات-ومهارات-البحث",
        "مهارات-الصناعة-وريادة-الأعمال",
    ],
}
tot = 0
for pdf in sorted((ROOT / "2-إعدادي" / "الصف-الأول").rglob("*.pdf")):
    subj = pdf.relative_to(ROOT / "2-إعدادي" / "الصف-الأول").parts[1]
    if subj not in picks["prep1"]:
        continue
    d = pymupdf.open(pdf)
    tot += d.page_count
    print(f"{pdf.stem:34} {d.page_count:4} صفحة  {pdf.stat().st_size/1048576:6.1f} MB")

for rel in ("الصف-الثالث/الترم-الأول/التربية-المسرحية", "الصف-الثاني/الترم-الأول/المكتبات-ومهارات-البحث"):
    for pdf in (ROOT / "2-إعدادي" / rel).rglob("*.pdf"):
        d = pymupdf.open(pdf)
        tot += d.page_count
        print(f"{pdf.stem:34} {d.page_count:4} صفحة  {pdf.stat().st_size/1048576:6.1f} MB")
print("إجمالي الصفحات:", tot)
