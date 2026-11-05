import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
queue = json.loads((ROOT / "scripts/convert/queue_prep_t1.json").read_text(encoding="utf-8"))

done, todo = [], []
for bid, rel, book, total, subject in queue:
    d = ROOT / "output" / book
    have = {int(p.stem.split("_")[1]) for p in d.glob("page_*.md")} if d.is_dir() else set()
    miss = [n for n in range(1, total + 1) if n not in have]
    if miss:
        todo.append([bid, rel, book, total, subject])
        print(f"{bid:30} ناقص {len(miss):3} صفحة {miss[:12]}{' …' if len(miss) > 12 else ''}")
    else:
        done.append(bid)

(ROOT / "scripts/convert/queue_prep_t1_resume.json").write_text(
    json.dumps(todo, ensure_ascii=False, indent=2), encoding="utf-8")
print("\nمكتملة الصفحات:", len(done), done)
print("في طابور الاستئناف:", len(todo))
