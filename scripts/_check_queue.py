import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "convert"))
import pipeline_all as pa

queue = [tuple(e) for e in json.loads((pa.ROOT / "scripts/convert/queue_prep_t1.json").read_text(encoding="utf-8"))]
ours = {e[0] for e in queue}
dup = {}
for e in queue:
    dup[e[3]] = dup.get(e[3], 0) + 1
missing_src = [e[0] for e in queue if not pa.resolve_src(e[1]).exists()]
missing_pdf = [e[0] for e in queue if not (pa.RAW / f"{e[2]}.pdf").exists()]
print("عدد الكتاب:", len(queue))
print("مصادر مفقودة:", missing_src or "لا شيء")
print("نسخ PDF غير موجودة بعد (طبيعي قبل التشغيل):", len(missing_pdf))
for e in queue:
    print(f"{e[0]:30} {e[3]:4} | {pa.book_title(e[2], e[4])}")
print("إجمالي الصفحات:", sum(e[3] for e in queue))
