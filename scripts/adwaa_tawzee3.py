#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
استخراج صفحات "توزيع المناهج" من كتب الأضواء على archive.org.

المراحل:
  1) manifest  : بناء قائمة كتب الأضواء (ترم أول) لكل الصفوف/المواد + تجهيز روابط PDF.
  2) download  : تنزيل كل كتاب (قابل للاستكمال: يعيد المحاولة ويكمل من حيث توقف).
  3) extract   : كشف صفحات التوزيع آليًا (صفحة رمادية + شبكة جداول) وتصديرها كملف PDF منفصل.
  4) report    : تقرير JSON + ملخص نصي بالحجم وعدد الصفحات والحالات.

الملفات:
  يقرأ/يكتب: workspace/manifest/adwaa_manifest.json
             workspace/logs/adwaa_report.json
  ينزّل إلى: <downloads>/_source/<slug>.pdf
  يصدّر إلى: <downloads>/<المرحلة>/<الصف>/<المادة>.pdf

الاستخدام:
  python scripts/adwaa_tawzee3.py manifest
  python scripts/adwaa_tawzee3.py download --workers 3
  python scripts/adwaa_tawzee3.py extract
  python scripts/adwaa_tawzee3.py report
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = ROOT / "manifest"
LOGS = ROOT / "logs"
OUT_ROOT = Path(os.environ.get("ADWAA_OUT", r"C:\Users\blals\Downloads\توزيع-المناهج-2026-2027"))
SRC_DIR = OUT_ROOT / "_source"

SEARCH_URL = "https://archive.org/advancedsearch.php"
META_URL = "https://archive.org/metadata/{id}"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/144.0"}

LAYER_ALLO = "https://api.allorigins.win/raw?url="
LAYER_CODE = "https://api.codetabs.com/v1/proxy?quest="
LAYER_JINA = "https://r.jina.ai/"
# archive.org الرئيسي محجوب على هذه الشبكة (TLS لا يكتمل) — مباشرة ممنوعة
LAYERS = (LAYER_JINA, LAYER_ALLO, LAYER_CODE)


def _strip_jina(text: str) -> str:
    marker = "Markdown Content:"
    i = text.find(marker)
    return text[i + len(marker):] if i >= 0 else text


def archive_get(url: str, params: dict | None = None, timeout: int = 60) -> dict:
    """GET على archive.org عبر وسطاء (jina ثم allorigins ثم codetabs). يعيد JSON محلولاً."""
    from urllib.parse import urlencode, quote
    full = url + ("?" + urlencode(params, doseq=True) if params else "")
    last = None
    for layer in LAYERS:
        for attempt in range(2):
            try:
                if layer is LAYER_JINA:
                    r = requests.get(LAYER_JINA + full, headers=UA, timeout=timeout)
                    r.raise_for_status()
                    return json.loads(_strip_jina(r.text))
                r = requests.get(layer + quote(full, safe=""), headers=UA, timeout=timeout)
                r.raise_for_status()
                return r.json()
            except Exception as exc:  # noqa: BLE001
                last = exc
                code = getattr(exc, "response", None) and getattr(exc.response, "status_code", 0)
                if code == 429:
                    time.sleep(4)
    raise ConnectionError(f"فشل كل الوسطاء: {last}")

# ---------- تطبيع النص العربي ----------
_DIAC = re.compile(r"[\u064B-\u0652\u0640]")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = _DIAC.sub("", s)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه"), ("ؤ", "و"), ("ئ", "ي")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


TERM1 = ("ترم اول", "الترم الاول", "ترم 1", "ترم1", "الفصل الدراسي الاول")
TERM2 = ("ترم ثان", "الترم الثانى", "الترم الثاني", "ترم 2", "ترم2", "ترم تانى", "ترم تاني", "الفصل الدراسي الثاني")
NOT_BOOK = ("نماذج", "امتحانات", "مراجع", "اجابات", "بنك", "اختبار", "ملخص", "مذكره ملخصه")

GRADES = [
    ("kg1", "رياض الأطفال", "مستوى أول", ("كي جي 1", "kg1", "كي جي وان")),
    ("kg2", "رياض الأطفال", "مستوى ثان", ("كي جي 2", "kg2", "كي جي تو")),
    ("p1", "الابتدائية", "الصف الأول الابتدائي", ("1 ابتدائي", "اولي ابتدائي", "اول ابتدائي", "الاول الابتدائي", "1ب", "1 ب ")),
    ("p2", "الابتدائية", "الصف الثاني الابتدائي", ("2 ابتدائي", "تانيه ابتدائي", "ثاني ابتدائي", "الثاني الابتدائي", "2ب")),
    ("p3", "الابتدائية", "الصف الثالث الابتدائي", ("3 ابتدائي", "تالته ابتدائي", "ثالث ابتدائي", "الثالث الابتدائي", "3ب")),
    ("p4", "الابتدائية", "الصف الرابع الابتدائي", ("4 ابتدائي", "رابعه ابتدائي", "رابع ابتدائي", "الرابع الابتدائي", "4ب")),
    ("p5", "الابتدائية", "الصف الخامس الابتدائي", ("5 ابتدائي", "خامسه ابتدائي", "خامس ابتدائي", "الخامس الابتدائي", "5ب")),
    ("p6", "الابتدائية", "الصف السادس الابتدائي", ("6 ابتدائي", "سادسه ابتدائي", "سادس ابتدائي", "السادس الابتدائي", "6ب")),
    ("m1", "الإعدادية", "الصف الأول الإعدادي", ("1 اعدادي", "اولي اعدادي", "اول اعدادي", "الاول الاعدادي", "1ع")),
    ("m2", "الإعدادية", "الصف الثاني الإعدادي", ("2 اعدادي", "تانيه اعدادي", "ثاني اعدادي", "الثاني الاعدادي", "2ع")),
    ("m3", "الإعدادية", "الصف الثالث الإعدادي", ("3 اعدادي", "تالته اعدادي", "ثالث اعدادي", "الثالث الاعدادي", "3ع")),
    ("s1", "الثانوي العام", "الصف الأول الثانوي", ("1 ثانوي", "اولي ثانوي", "اول ثانوي", "الاول الثانوي", "1ث")),
    ("s2", "الثانوي العام", "الصف الثاني الثانوي", ("2 ثانوي", "تانيه ثانوي", "ثاني ثانوي", "الثاني الثانوي", "2ث")),
    ("s3", "الثانوي العام", "الصف الثالث الثانوي", ("3 ثانوي", "تالته ثانوي", "ثالث ثانوي", "الثالث الثانوي", "3ث")),
]

SUBJECTS = [
    ("اللغة العربية", ("لغه عربيه", "لغة عربية", "عربي", "العربيه")),
    ("اللغة الإنجليزية", ("لغه انجليزيه", "لغة انجليزية", "انجليزي", "english", "كونكت", "connect")),
    ("الرياضيات", ("رياضيات", "ماث", "math")),
    ("العلوم", ("علوم", "ساينس", "science")),
    ("الدراسات الاجتماعية", ("دراسات", "اجتماعيات")),
    ("التربية الدينية", ("تربيه دينيه", "تربية دينية", "دين", "اسلامي")),
    ("اللغة الفرنسية", ("فرنساوي", "فرنسي", "francais", "français")),
    ("اللغة الألمانية", ("الماني", "ألماني")),
    ("اللغة الإسبانية", ("اسباني", "إسباني")),
    ("اللغة الإيطالية", ("ايطالي", "إيطالي")),
    ("التاريخ", ("تاريخ",)),
    ("الجغرافيا", ("جغرافيا",)),
    ("الفلسفة والمنطق", ("فلسفه", "فلسفة", "منطق")),
    ("علم النفس والاجتماع", ("علم نفس", "اجتماع", "نفس")),
    ("الفيزياء", ("فيزياء",)),
    ("الكيمياء", ("كيمياء",)),
    ("الأحياء", ("احياء", "أحياء")),
    ("الجيولوجيا", ("جيولوجيا",)),
    ("الرياضيات البحتة", ("بحته", "بحتة", "تفاضل", "جبر", "هندسه فراغيه", "استاتيكا", "ديناميكا")),
    ("الإحصاء", ("احصاء", "إحصاء")),
    ("علوم متكاملة", ("علوم متكامله", "علوم متكاملة", "integrated")),
    ("الحاسب والبرمجة", ("حاسب", "برمجه", "برمجة", "تكنولوجيا المعلومات", "ict")),
    ("المهارات المهنية", ("مهارات", "مهني")),
    ("القيم واحترام الآخر", ("قيم", "احترام")),
]


def classify(title: str):
    t = " " + norm(title) + " "
    key = stage = grade = None
    for gkey, gstage, gname, alts in GRADES:
        if any((" " + norm(a) + " ") in t or norm(a) in t for a in alts):
            key, stage, grade = gkey, gstage, gname
            break
    subj = None
    for name, alts in SUBJECTS:
        if any(norm(a) in t for a in alts):
            subj = name
            break
    return key, stage, grade, subj


def season_score(title: str) -> int:
    t = norm(title)
    if "2027" in t:
        return 3
    if "2026" in t:
        return 2
    if "2025" in t:
        return 1
    return 0


def search_all(query: str, rows: int = 300) -> list:
    docs, page = [], 1
    while len(docs) < rows:
        params = {
            "q": query,
            "fl[]": ["identifier", "title", "publicdate", "item_size"],
            "rows": 100,
            "page": page,
            "output": "json",
            "sort[]": "publicdate desc",
        }
        r = archive_get(SEARCH_URL, params=params)
        resp = r["response"]
        batch = [x for x in resp["docs"] if x.get("identifier")]
        docs.extend(batch)
        if not batch or len(docs) >= resp["numFound"]:
            break
        page += 1
    return docs


def pick_pdfs(meta: dict) -> list:
    files = meta.get("files", [])
    out = []
    for f in files:
        name = f.get("name", "")
        if not name.lower().endswith(".pdf"):
            continue
        if name.lower().endswith("_text.pdf"):
            continue
        out.append({
            "name": name,
            "size": int(f.get("size") or 0),
            "url": f"https://{meta['server']}{meta['dir']}/{requests.utils.quote(name)}",
        })
    return out


def build_manifest():
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    queries = [
        'title:(الاضواء) AND mediatype:texts',
        'title:(الاضواء) AND title:(ترم) AND mediatype:texts',
    ]
    docs, seen = [], set()
    for q in queries:
        try:
            for d in search_all(q):
                if not d.get("identifier"):
                    print(f"! رجل بلا معرف (تخطي): {str(list(d.keys()))[:120]}", flush=True)
                    continue
                if d["identifier"] not in seen:
                    seen.add(d["identifier"])
                    docs.append(d)
        except Exception as exc:  # noqa: BLE001
            print(f"! فشل البحث: {q} — {exc}", flush=True)

    print(f"عناصر مرشّحة من البحث: {len(docs)}", flush=True)

    entries = []
    for d in docs:
        title = d.get("title", "") or ""
        t = norm(title)
        if "الاضواء" not in t and "اضواء" not in t:
            continue
        if not any(k in t for k in TERM1):
            continue
        if any(k in t for k in TERM2):
            continue
        if any(k in t for k in NOT_BOOK):
            continue
        gkey, stage, grade, subj = classify(title)
        if not gkey:
            continue
        try:
            meta = archive_get(META_URL.format(id=d["identifier"]))
        except Exception as exc:  # noqa: BLE001
            print(f"! meta فشل: {d['identifier']} — {exc}", flush=True)
            continue
        for pdf in pick_pdfs(meta):
            if pdf["size"] < 2_000_000:
                continue
            p_gkey, p_stage, p_grade, p_subj = classify(pdf["name"])
            use_g = (p_gkey or gkey), (p_grade or grade), (p_stage or stage)
            entries.append({
                "id": d["identifier"],
                "item_title": title,
                "pdf": pdf["name"],
                "size": pdf["size"],
                "url": pdf["url"],
                "publicdate": d.get("publicdate", ""),
                "gkey": use_g[0],
                "grade": use_g[1],
                "stage": use_g[2],
                "subject": p_subj or subj or "غير محدد",
                "season": season_score(title),
            })
        time.sleep(3.2)

    # إزالة التكرار: (صف، مادة) مع تفضيل أحدث موسم ثم الأكبر حجمًا
    best = {}
    for e in entries:
        k = (e["gkey"], e["subject"])
        cur = best.get(k)
        if cur is None or (e["season"], e["size"]) > (cur["season"], cur["size"]):
            best[k] = e
    final = sorted(best.values(), key=lambda x: (x["gkey"], x["subject"]))

    out = MANIFEST_DIR / "adwaa_manifest.json"
    out.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    total_mb = sum(e["size"] for e in final) / 2**20
    print(f"كتب مختارة: {len(final)} — {total_mb:,.0f} MB", flush=True)
    print(f"القائمة: {out}", flush=True)
    return final


def load_manifest():
    p = MANIFEST_DIR / "adwaa_manifest.json"
    if not p.exists():
        build_manifest()
    return json.loads(p.read_text(encoding="utf-8"))


def slug(e):
    base = f"{e['gkey']}-{norm(e['subject']).replace(' ', '-')}-{e['id'][-8:]}"
    return re.sub(r"[^0-9A-Za-z\-\u0600-\u06FF]", "", base)


def download_one(e, attempts=8):
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    dest = SRC_DIR / (slug(e) + ".pdf")
    if dest.exists() and dest.stat().st_size >= e["size"] * 0.995:
        return {"status": "موجود", "path": str(dest), "size": dest.stat().st_size}
    for i in range(attempts):
        have = dest.stat().st_size if dest.exists() else 0
        headers = dict(UA)
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with requests.get(e["url"], headers=headers, stream=True, timeout=(30, 120)) as r:
                if r.status_code == 416:
                    break
                r.raise_for_status()
                mode = "ab" if have and r.status_code == 206 else "wb"
                with dest.open(mode) as fh:
                    for chunk in r.iter_content(1 << 20):
                        if chunk:
                            fh.write(chunk)
        except Exception:  # noqa: BLE001
            time.sleep(2 + i)
            continue
        if dest.exists() and dest.stat().st_size >= e["size"] * 0.995:
            break
        time.sleep(2 + i)
    ok = dest.exists() and dest.stat().st_size >= e["size"] * 0.99
    with dest.open("rb") as fh:
        head = fh.read(5)
    ok = ok and head == b"%PDF-"
    return {"status": "نُزّل" if ok else "فشل", "path": str(dest),
            "size": dest.stat().st_size if dest.exists() else 0}


def cmd_download(workers=3):
    books = load_manifest()
    LOGS.mkdir(parents=True, exist_ok=True)
    results = []
    total = len(books)
    print(f"تنزيل {total} كتابًا ...", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(download_one, e): e for e in books}
        for n, fut in enumerate(as_completed(futs), 1):
            e = futs[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                res = {"status": "فشل", "error": str(exc)[:200]}
            res.update({"grade": e["grade"], "subject": e["subject"], "id": e["id"], "pdf": e["pdf"], "url": e["url"]})
            results.append(res)
            mb = (res.get("size") or 0) / 2**20
            print(f"[{n}/{total}] {res['status']:<6} {mb:6.1f} MB  {e['grade']} | {e['subject']}", flush=True)
    report = LOGS / "adwaa_report_download.json"
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    done = sum(1 for r in results if r["status"] in ("نُزّل", "موجود"))
    gb = sum(r.get("size") or 0 for r in results) / 2**30
    print(f"تم: {done}/{total} — {gb:.2f} GB — تقرير: {report}", flush=True)


# ---------- كشف صفحات التوزيع ----------
def page_signals(page, dpi=72):
    """يعيد (التشبع اللوني، عدد الخطوط الأفقية، عدد الخطوط الرأسية) — بمقياس حبر خفيف يشمل خطوط الجداول الفاتحة."""
    import numpy as np

    pix = page.get_pixmap(dpi=dpi)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    rgb = a[:, :, :3].astype(np.int16)
    sat = float((rgb.max(axis=2) - rgb.min(axis=2)).mean())
    gray = a[:, :, 0] if pix.n == 1 else (
        0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2])
    ink = gray < 250
    horiz = int((ink.mean(axis=1) > 0.80).sum())
    vert = int((ink.mean(axis=0) > 0.80).sum())
    return sat, horiz, vert


def detect_pages(path, max_pages=None, sat_max=255.0, min_h=5, min_v=4):
    """يعيد أرقام الصفحات (1-based) ذات شبكة جدول واضحة في أول الكتاب — صفحات التوزيع."""
    import pymupdf

    doc = pymupdf.open(path)
    try:
        n = doc.page_count if max_pages is None else min(max_pages, doc.page_count)
        hits = []
        for i in range(n):
            try:
                _sat, h, v = page_signals(doc[i])
            except Exception:  # noqa: BLE001
                continue
            if h >= min_h and v >= min_v:
                hits.append(i + 1)
        return hits
    finally:
        doc.close()


def export_pages(path, pages, dest):
    import pymupdf

    dest.parent.mkdir(parents=True, exist_ok=True)
    src = pymupdf.open(path)
    out = pymupdf.open()
    try:
        for p in pages:
            out.insert_pdf(src, from_page=p - 1, to_page=p - 1)
        out.save(str(dest), deflate=True, garbage=3)
    finally:
        out.close()
        src.close()


def cmd_extract(only=None, sat_max=12.0, scan_pages=20):
    import pymupdf  # noqa: F401  (تحقق من التوفر مبكرًا)

    books = load_manifest()
    reports = []
    used = set()
    for idx, e in enumerate(books, 1):
        src = SRC_DIR / (slug(e) + ".pdf")
        if not src.exists():
            reports.append({"grade": e["grade"], "subject": e["subject"], "status": "غير منزّل"})
            continue
        if only and only not in str(src):
            continue
        try:
            pages = detect_pages(str(src), max_pages=scan_pages, sat_max=sat_max)
        except Exception as exc:  # noqa: BLE001
            reports.append({"grade": e["grade"], "subject": e["subject"], "status": f"خطأ: {exc}"[:120]})
            continue
        if not pages:
            reports.append({"grade": e["grade"], "subject": e["subject"], "status": "لا توجد صفحة توزيع",
                            "pages": 0})
            print(f"[{idx}/{len(books)}] -     {e['grade']} | {e['subject']} : لا توجد", flush=True)
            continue
        name = f"{e['subject']}.pdf"
        folder = OUT_ROOT / e["stage"] / e["grade"]
        dest = folder / name
        stem = 2
        while dest in used or dest.exists():
            dest = folder / f"{e['subject']} ({stem}).pdf"
            stem += 1
        used.add(dest)
        export_pages(str(src), pages, dest)
        size = dest.stat().st_size
        reports.append({
            "grade": e["grade"], "stage": e["stage"], "subject": e["subject"],
            "status": "تم", "pages_found": pages, "pages": len(pages),
            "size": size, "path": str(dest), "source_url": e["url"], "source_size": e["size"],
        })
        print(f"[{idx}/{len(books)}] + {len(pages)} صفحة {size/2**20:5.2f} MB  {e['grade']} | {e['subject']}  صفحات {pages}",
              flush=True)

    LOGS.mkdir(parents=True, exist_ok=True)
    rep = LOGS / "adwaa_report.json"
    rep.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = [r for r in reports if r.get("status") == "تم"]
    print(f"استُخرج التوزيع من {len(ok)} كتابًا — {sum(r['size'] for r in ok)/2**20:,.1f} MB — تقرير: {rep}",
          flush=True)


def cmd_candidates(sat_max=12.0, min_h=10, min_v=5, scan_pages=20):
    """يستخرج الصفحات المرشّحة كصور مصغّرة + لوحات مراجعة مجمّعة."""
    import pymupdf
    from PIL import Image, ImageDraw

    books = load_manifest()
    cand_dir = ROOT / "cache" / "adwaa_candidates"
    sheet_dir = ROOT / "cache" / "adwaa_sheets"
    cand_dir.mkdir(parents=True, exist_ok=True)
    sheet_dir.mkdir(parents=True, exist_ok=True)

    records = []
    n = 0
    for idx, e in enumerate(books, 1):
        src = SRC_DIR / (slug(e) + ".pdf")
        if not src.exists():
            continue
        doc = pymupdf.open(src)
        try:
            for i in range(min(scan_pages, doc.page_count)):
                sat, h, v = page_signals(doc[i])
                if sat < sat_max and h >= min_h and v >= min_v:
                    n += 1
                    pix = doc[i].get_pixmap(dpi=110)
                    png = cand_dir / f"{n:04d}.png"
                    pix.save(str(png))
                    records.append({
                        "n": n, "book": idx, "grade": e["grade"], "stage": e["stage"],
                        "subject": e["subject"], "page": i + 1, "sat": round(sat, 1),
                        "h": h, "v": v, "png": str(png), "src": str(src), "url": e["url"],
                    })
        finally:
            doc.close()
        print(f"[{idx}/{len(books)}] {e['grade']} | {e['subject']} — مرشّحات: {n}", flush=True)

    (ROOT / "manifest" / "adwaa_candidates.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    # لوحات 4×3 مع أرقام
    cols, rows, tw = 4, 3, 420
    per = cols * rows
    for s in range(0, len(records), per):
        chunk = records[s:s + per]
        thumbs = []
        for r in chunk:
            im = Image.open(r["png"]).convert("RGB")
            k = tw / im.width
            im = im.resize((tw, int(im.height * k)))
            thumbs.append((r["n"], im))
        th = max(t[1].height for t in thumbs) + 26
        sheet = Image.new("RGB", (cols * tw, rows * th), "white")
        dr = ImageDraw.Draw(sheet)
        for j, (num, im) in enumerate(thumbs):
            x, y = (j % cols) * tw, (j // cols) * th
            sheet.paste(im, (x, y + 26))
            dr.text((x + 6, y + 6), f"#{num}", fill="black")
        out = sheet_dir / f"sheet_{s // per + 1:02d}.png"
        sheet.save(out)
        print(f"لوحة: {out}", flush=True)

    print(f"مرشّحات: {len(records)} صفحة — خريطة: manifest/adwaa_candidates.json", flush=True)


def cmd_final(selection_json):
    """يبني ملفات التوزيع النهائية من الصفحات المعتمدة (أرقام المرشّحات)."""
    sel_path = Path(selection_json)
    selected = json.loads(sel_path.read_text(encoding="utf-8"))
    recs = json.loads((ROOT / "manifest" / "adwaa_candidates.json").read_text(encoding="utf-8"))
    by_n = {r["n"]: r for r in recs}

    groups = {}
    for n in selected:
        r = by_n[n]
        groups.setdefault(r["book"], []).append(r)

    reports, used = [], set()
    for book in sorted(groups):
        items = sorted(groups[book], key=lambda r: r["page"])
        first = items[0]
        folder = OUT_ROOT / first["stage"] / first["grade"]
        dest = folder / f"{first['subject']}.pdf"
        stem = 2
        while dest in used or dest.exists():
            dest = folder / f"{first['subject']} ({stem}).pdf"
            stem += 1
        used.add(dest)
        export_pages(first["src"], [r["page"] for r in items], dest)
        reports.append({
            "stage": first["stage"], "grade": first["grade"], "subject": first["subject"],
            "pages": [r["page"] for r in items], "size": dest.stat().st_size,
            "path": str(dest), "source_url": first["url"],
        })
        print(f"+ {first['grade']} | {first['subject']} — صفحات {[r['page'] for r in items]} — "
              f"{dest.stat().st_size/2**20:.2f} MB", flush=True)

    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "adwaa_final.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(r["size"] for r in reports) / 2**20
    print(f"ملفات نهائية: {len(reports)} — {total:.1f} MB", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["manifest", "download", "extract", "candidates", "final"])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--only", default=None)
    ap.add_argument("--sat-max", type=float, default=12.0)
    ap.add_argument("--scan-pages", type=int, default=20)
    ap.add_argument("--selection", default=None)
    args = ap.parse_args()
    if args.cmd == "manifest":
        build_manifest()
    elif args.cmd == "download":
        cmd_download(args.workers)
    elif args.cmd == "extract":
        cmd_extract(args.only, args.sat_max, args.scan_pages)
    elif args.cmd == "candidates":
        cmd_candidates(args.sat_max, 10, 5, args.scan_pages)
    elif args.cmd == "final":
        cmd_final(args.selection)
