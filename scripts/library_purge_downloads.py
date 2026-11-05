# -*- coding: utf-8 -*-
"""
حذف نسخ التنزيلات بعد التأكد من وجودها في المكتبة بصمةً بحجم واحد (SHA256).

يمرّ على كل كتب المكتبة التي مصدرها مجلد التنزيلات، ويقارن البصمة،
ثم ينقل الأصل إلى سلة المحذوفات (لا حذف نهائي).

التشغيل:
    python scripts/library_purge_downloads.py            # فحص فقط (dry-run)
    python scripts/library_purge_downloads.py --apply    # تنفيذ
"""
import hashlib
import sys
from pathlib import Path

import yaml

LIB = Path(r"D:\المكتبة-التعليمية")
SRC = Path(r"C:\Users\blals\Downloads\Arabic-T1-2026-2027")
INDEX = LIB / "_الفهرس.yaml"

# مسار المكتبة (نسبي) ← مسار التنزيلات (نسبي إلى SRC)
MAP = {
    "1ب-عربي-وزارة-كتاب-2027.pdf": "StudentBook/01-Primary/Arabic-G1-Primary-T1-StudentBook.pdf",
    "2ب-عربي-وزارة-كتاب-2027.pdf": "StudentBook/01-Primary/Arabic-G2-Primary-T1-StudentBook.pdf",
    "3ب-عربي-وزارة-كتاب-2027.pdf": "StudentBook/01-Primary/Arabic-G3-Primary-T1-StudentBook.pdf",
    "4ب-عربي-وزارة-كتاب-2027.pdf": "StudentBook/01-Primary/Arabic-G4-Primary-T1-StudentBook.pdf",
    "5ب-عربي-وزارة-كتاب-2027.pdf": "StudentBook/01-Primary/Arabic-G5-Primary-T1-StudentBook.pdf",
    "6ب-عربي-وزارة-كتاب-2027.pdf": "StudentBook/01-Primary/Arabic-G6-Primary-T1-StudentBook.pdf",
    "1ع-عربي-وزارة-كتاب-2027.pdf": "StudentBook/02-Preparatory/Arabic-G7-Preparatory-T1-StudentBook.pdf",
    "2ع-عربي-وزارة-كتاب-2027.pdf": "StudentBook/02-Preparatory/Arabic-G8-Preparatory-T1-StudentBook.pdf",
    "3ع-عربي-وزارة-كتاب-2027.pdf": "StudentBook/02-Preparatory/Arabic-G9-Preparatory-T1-StudentBook.pdf",
    "1ث-عربي-وزارة-كتاب-2027.pdf": "StudentBook/03-Secondary/Arabic-S1-First-T1-StudentBook.pdf",
    "2ث-عربي-وزارة-كتاب-2027.pdf": "StudentBook/03-Secondary/Arabic-S2-Second-T1-StudentBook.pdf",
    "3ث-عربي-وزارة-كتاب-2027.pdf": "StudentBook/03-Secondary/Arabic-S3-Third-T1-StudentBook.pdf",
}
for i, code in enumerate(["1ب", "2ب", "3ب", "4ب", "5ب", "6ب"], start=1):
    MAP[f"{code}-عربي-وزارة-تقييم-2027.pdf"] = f"Assessments/01-Primary/Arabic-G{i}-Primary-T1-Assessments.pdf"
for i, code in [(7, "1ع"), (8, "2ع"), (9, "3ع")]:
    MAP[f"{code}-عربي-وزارة-تقييم-2027.pdf"] = f"Assessments/02-Preparatory/Arabic-G{i}-Preparatory-T1-Assessments.pdf"
for code, idx in [("1ث", 1), ("2ث", 2)]:
    for w in range(1, 8):
        MAP[f"{code}-عربي-وزارة-تقييم-أ{w:02d}-2027.pdf"] = \
            f"Assessments/03-Secondary/Arabic-Sec{idx}-T1-Week{w}-Assessment.pdf"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    apply = "--apply" in sys.argv
    books = yaml.safe_load(INDEX.read_text(encoding="utf-8"))["books"]
    seen, ok, bad, freed = set(), [], [], 0

    for book in books:
        name = Path(book["path"]).name
        src_rel = MAP.get(name)
        if not src_rel:
            continue
        seen.add(name)
        src = SRC / src_rel
        lib = LIB / book["path"]
        if not src.is_file():
            bad.append((name, "غير موجود في التنزيلات"))
            continue
        if sha256(src) != sha256(lib) or book["sha256"] != sha256(lib):
            bad.append((name, "البصمة مختلفة — أُبقي"))
            continue
        size = src.stat().st_size
        ok.append((name, src, size))
        freed += size

    print(f"مطابق: {len(ok)} | مستبعَد: {len(bad)} | كتب في الفهرس بلا مصدر معروف: {len(books) - len(seen)}")
    for name, reason in bad:
        print("  !", name, "—", reason)

    if not apply:
        print(f"\n[فحص فقط] سيُفرَّغ {freed / 1048576:.1f} MB. أضف --apply للتنفيذ.")
        return 0

    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION = 3, 0x0004, 0x0010
    FOF_ALLOWUNDO, FOF_NOERRORUI = 0x0040, 0x0400

    paths = "\0".join(str(p) for _, p, _ in ok) + "\0\0"
    op = SHFILEOPSTRUCTW(None, FO_DELETE, paths, None,
                         FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI, False, None, None)
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    print(f"SHFileOperation rc={rc} (0 = نجاح) — نُقلت {len(ok)} ملفًا إلى سلة المحذوفات ({freed / 1048576:.1f} MB)")

    left = list(SRC.rglob("*.pdf"))
    print(f"PDF متبقٍّ في مجلد التنزيلات: {len(left)}")
    for p in left:
        print("  -", p.relative_to(SRC).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
