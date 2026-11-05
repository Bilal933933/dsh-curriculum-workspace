#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
normalize.py — تطبيع نص عربي للبحث في فهرس الكتب.

الغرض:
    البحث في الكتب المحوَّلة يقتضي مطابقة نص المستخدم (غالبًا بلا تشكيل)
    مع نص مُشكَّل. هذا السكريبت يطبّع عبارة البحث بنفس قواعد build_index.py
    كي تُطابق ملفات index/<book>/norm/.

الاستخدام:
    python scripts/normalize.py "الاستعارة المكنية"
    echo "الاستعارة" | python scripts/normalize.py

لا يقرأ ولا يكتب أي ملف.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_index import normalize  # noqa: E402  (نفس قواعد الفهرسة)


def main() -> int:
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()
    result = normalize(text)
    if not result:
        print("[!] لم يتبقَّ نص بعد التطبيع", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
