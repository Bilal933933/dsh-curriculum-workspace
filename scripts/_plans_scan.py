import re
from pathlib import Path

import pymupdf

B = Path(r"C:\Users\blals\Downloads\توزيع-المناهج-2026-2027")
T = Path(r"C:\Users\blals\AppData\Local\Temp\opencode\tawzee")

rows = []
for stage in ("رياض الأطفال", "الابتدائية", "الإعدادية", "الثانوي العام"):
    for pdf in sorted((B / stage).rglob("*.pdf")):
        d = pymupdf.open(pdf)
        text = "".join(d[i].get_text() for i in range(min(3, d.page_count)))
        rows.append((stage, pdf.relative_to(B).as_posix(), d.page_count,
                     len(text.strip()), pdf.stat().st_size / 1048576))

print(f"{'المرحلة':14} {'صفحات':>6} {'نص':>7} {'MB':>6}  الملف")
for r in sorted(rows):
    print(f"{r[0]:14} {r[2]:6} {r[3]:7} {r[4]:6.1f}  {r[1]}")
print("\nعدد ملفات المراحل الأربع:", len(rows), "| صفحات:", sum(r[2] for r in rows))
print("فيها طبقة نصية:", sum(1 for r in rows if r[3] > 50), "| صور فقط:", sum(1 for r in rows if r[3] <= 50))

imgs = [p for p in T.rglob("*") if p.suffix.lower() in (".jpg", ".png", ".jpeg")]
pdfs = [p for p in T.rglob("*.pdf")]
print("\nتوزيعات الصور:", len(imgs), "| PDF:", len(pdfs), [p.name for p in pdfs])
for p in pdfs:
    d = pymupdf.open(p)
    print(f"  {p.name}: {d.page_count} صفحة")
