# -*- coding: utf-8 -*-
"""
تنزيل كتب الوزارة (الفصل الدراسي الأول) من المكتبة الإلكترونية الرسمية.

المصدر (قراءة فقط): https://ellibrary.moe.gov.eg/Books/<stage>/books.json
الهدف  (كتابة)    : C:\\Users\\blals\\Downloads\\كتب-الوزارة-2026-2027\\الترم-الأول

ما يفعله:
  1) يقرأ فهرس الكتب الرسمي لكل مرحلة (ابتدائي/إعدادي/ثانوي) ويصفّي الترم الأول.
  2) يفحص حجم كل ملف (HEAD) ويجمع الإجمالي قبل التنزيل، ويرفض إن تجاوز المساحة المتاحة.
  3) ينزّل بـ4 مسارات متوازية مع استكمال (.part) وإعادة محاولة.
  4) يتحقق أن الملف PDF صالح (%PDF) وأن حجمه مطابق.
  5) يكتب تقريرًا JSON: نُزِّل / موجود / فشل.

التشغيل:
  python scripts/download_books.py --dry-run     # فحص فقط: العدد والحجم
  python scripts/download_books.py               # تنزيل فعلي
  python scripts/download_books.py --only "الصف الأول الثانوي"
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

BASE = "https://ellibrary.moe.gov.eg/Books"
STAGES = ["Books-Primary", "Books-Preparatory", "Books-sec"]
TERM_FIRST = "الأول"

DEST_ROOT = Path(r"C:\Users\blals\Downloads\كتب-الوزارة-2026-2027\الترم-الأول")
REPORT = Path(__file__).resolve().parents[1] / "logs" / "download_books.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "*/*",
}
TIMEOUT = (20, 120)
RETRIES = 5
BAD_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def safe_name(text: str, limit: int = 110) -> str:
    """اسم ملف صالح على ويندوز."""
    name = BAD_CHARS.sub("-", str(text))
    name = re.sub(r"\s+", " ", name).strip(" .-")
    return name[:limit].strip(" .-") or "بدون-اسم"


def fetch_catalog(stages=None) -> list[dict]:
    """يقرأ books.json لكل مرحلة ويعيد كتب الترم الأول فقط."""
    books, seen = [], set()
    for stage in (stages or STAGES):
        url = f"{BASE}/{stage}/books.json"
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError(f"صيغة غير صحيحة: {url}")
        for item in data:
            if TERM_FIRST not in str(item.get("term", "")):
                continue
            link = str(item.get("link", "")).strip()
            if not link or link in seen:
                continue
            seen.add(link)
            books.append({
                "stage": str(item.get("stage", "")).strip(),
                "grade": str(item.get("grade", "")).strip(),
                "subject": str(item.get("subject", "")).strip(),
                "term": str(item.get("term", "")).strip(),
                "type": str(item.get("type", "")).strip(),
                "url": link,
            })
    return books


def probe(book: dict) -> dict:
    """HEAD لمعرفة الحجم قبل التنزيل."""
    for attempt in range(1, RETRIES + 1):
        try:
            resp = requests.head(book["url"], headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            if resp.status_code == 200:
                book["bytes"] = int(resp.headers.get("Content-Length") or 0)
                return book
            book["error"] = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            book["error"] = f"{type(exc).__name__}: {exc}"
        time.sleep(attempt * 5)
    book.setdefault("bytes", 0)
    return book


def target_path(book: dict) -> Path:
    return (DEST_ROOT / safe_name(book["stage"]) / safe_name(book["grade"])
            / f"{safe_name(book['subject'])}.pdf")


def download(book: dict) -> dict:
    """ينزّل ملفًا واحدًا مع استكمال وفحص."""
    dest = target_path(book)
    book["path"] = str(dest)
    expected = book.get("bytes") or 0

    if dest.is_file() and dest.stat().st_size > 1024 and (not expected or dest.stat().st_size == expected):
        book["status"] = "موجود"
        return book

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".pdf.part")

    for attempt in range(1, RETRIES + 1):
        try:
            done = part.stat().st_size if part.is_file() else 0
            if expected and done > expected:
                part.unlink()
                done = 0
            headers = dict(HEADERS)
            if done:
                headers["Range"] = f"bytes={done}-"
            with requests.get(book["url"], headers=headers, stream=True, timeout=TIMEOUT) as resp:
                if resp.status_code == 416:          # الملف مكتمل
                    pass
                elif resp.status_code not in (200, 206):
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                else:
                    mode = "ab" if (resp.status_code == 206 and done) else "wb"
                    with open(part, mode) as fh:
                        for chunk in resp.iter_content(1 << 20):
                            if chunk:
                                fh.write(chunk)

            if not part.is_file() or part.stat().st_size == 0:
                raise IOError("ملف فارغ")
            with open(part, "rb") as fh:
                if fh.read(5)[:4] != b"%PDF":
                    part.unlink()
                    raise IOError("ليس PDF صالحًا")
            if expected and part.stat().st_size != expected:
                raise IOError(f"حجم ناقص {part.stat().st_size}/{expected}")

            os.replace(part, dest)
            book["status"] = "نُزِّل"
            book["size_mb"] = round(dest.stat().st_size / (1 << 20), 1)
            return book
        except Exception as exc:  # noqa: BLE001 — نسجّل ونعيد المحاولة
            book["error"] = f"{type(exc).__name__}: {exc}"
            time.sleep(attempt * 5)

    book["status"] = "فشل"
    return book


def free_bytes(path: Path) -> int:
    probe_path = path
    while not probe_path.exists() and probe_path.parent != probe_path:
        probe_path = probe_path.parent
    return shutil.disk_usage(probe_path).free


def main() -> int:
    parser = argparse.ArgumentParser(description="تنزيل كتب الوزارة — الترم الأول")
    parser.add_argument("--dry-run", action="store_true", help="فحص العدد والحجم فقط")
    parser.add_argument("--only", default="", help="تصفية باسم صف أو مادة")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--with-kg", action="store_true", help="تضمين رياض الأطفال")
    args = parser.parse_args()

    stages = STAGES + (["Books-Kindergarten"] if args.with_kg else [])
    books = fetch_catalog(stages)
    if args.only:
        books = [b for b in books if args.only in b["grade"] or args.only in b["subject"]]
    if not books:
        print("لا توجد كتب مطابقة.")
        return 1

    print(f"عدد الكتب: {len(books)} — جارٍ فحص الأحجام ...")
    with ThreadPoolExecutor(max_workers=8) as pool:
        books = list(pool.map(probe, books))

    total = sum(b.get("bytes", 0) for b in books)
    missing = [b for b in books if not b.get("bytes")]
    print(f"الإجمالي: {total / (1 << 30):.2f} GB"
          + (f" — بلا حجم معروف: {len(missing)}" if missing else ""))

    if args.dry_run:
        for b in books:
            print(f"{b.get('bytes', 0) / (1 << 20):8.1f} MB  {b['grade']} | {b['subject']}")
        return 0

    DEST_ROOT.mkdir(parents=True, exist_ok=True)
    available = free_bytes(DEST_ROOT)
    if total and total > available * 0.85:
        print(f"! المساحة غير كافية: مطلوب {total / (1 << 30):.2f} GB "
              f"والمتاح {available / (1 << 30):.2f} GB — أُلغي.")
        return 2

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(download, b): b for b in books}
        for i, fut in enumerate(as_completed(futures), 1):
            book = fut.result()
            results.append(book)
            mb = book.get("size_mb") or round((book.get("bytes") or 0) / (1 << 20), 1)
            print(f"[{i:>3}/{len(books)}] {book['status']:<7} {mb:>7.1f} MB  "
                  f"{book['grade']} | {book['subject']}"
                  + (f"  ← {book['error']}" if book["status"] == "فشل" else ""))

    counts = {}
    for book in results:
        counts[book["status"]] = counts.get(book["status"], 0) + 1
    got = sum(1 for b in results if b["status"] in ("نُزِّل", "موجود"))
    size = sum((b.get("size_mb") or 0) for b in results if b["status"] in ("نُزِّل", "موجود"))

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "root": str(DEST_ROOT),
        "total_books": len(results),
        "counts": counts,
        "total_size_mb": round(size, 1),
        "books": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nتمّ: {got}/{len(results)} — {counts} — {size:.0f} MB\nتقرير: {REPORT}")
    print(f"المسار: {DEST_ROOT}")
    return 0 if got == len(results) else 3


if __name__ == "__main__":
    sys.exit(main())
