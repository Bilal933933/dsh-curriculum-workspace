# -*- coding: utf-8 -*-
"""
استئناف خطوتي التسجيل المتوقفين (فهرسة + مسوّدة خريطة) لكتاب تسجّل مدخله
في catalog.yaml ثم انهار السكربت قبل بناء الفهرس بسبب ترميز الطباعة.

الاستخدام:
    python scripts/_onboard_resume.py --id math_prep3_t1 --dir "الرياضيات_الصف_الثالث_الإعدادي_ت1" --title "العنوان"
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # workspace/
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "retrieval"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import onboard_book as ob  # توظيف دوال السكربت الرسمي ذاتها


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--dir", required=True, help="اسم مجلد الكتاب في output/")
    ap.add_argument("--title", required=True)
    args = ap.parse_args()

    book_dir = ob.OUTPUT_DIR / args.dir
    if not book_dir.is_dir():
        print(f"لا يوجد مجلد: {book_dir}")
        return 1

    m = ob.build_book(book_dir)
    print(f"[✓] فهرس: {m['pages_indexed']} صفحة | {m['normalized_chars']:,} حرفًا")

    dest = ob.META_BOOKS / args.id
    dest.mkdir(parents=True, exist_ok=True)
    draft = dest / "toc.draft.yaml"
    draft.write_text(ob.toc_draft(book_dir, args.id, args.title), encoding="utf-8")
    print(f"[✓] مسوّدة: {draft.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
