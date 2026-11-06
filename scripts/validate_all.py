#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
حارس مساحة العمل (workspace guard)
==================================
سبع قواعد كانت نصوصًا تُقرأ على أمل أن يتذكّرها الوكيل، صارت فحصًا يفشل بصوت عالٍ.

القواعد المفحوصة
-----------------
1. env_hygiene            : .env غير متتبَّع ومستثنى في .gitignore (داخل مستودع فعلي).
2. doc_paths             : كل مسار مذكور في AGENTS.md والمهارات موجود فعلًا.
3. skill_frontmatter     : لكل SKILL.md ترويسة YAML باسم يطابق مجلده ووصف دالّ.
4. no_silent_book_default: لا `--book` بافتراضي صامت في سكريبتات التحويل/المراجعة.
5. pages_converted       : pages_converted في catalog.yaml يطابق عدد الملفات الفعلي.
6. topics_baseline       : عدد موضوعات كل toc.yaml لم ينحدر عن خط الأساس.
7. orphan_dirs           : (تحذير) مجلدات في output/ أو index/ بلا اعتماد في المرجع.
8. source_hash           : (بـ --check-hash) بصمة output/ و index/ لم تتغيّر بلا تصريح.

الفلسفة
-------
- لا يعتمد على PDF ولا على curriculum_raw: كل الأعداد من catalog.yaml.
- لا يقارن `id` (لاتيني) بأسماء المجلدات (عربية) — المقارنة عبر text_dir/index_dir حصرًا.
  (هذا هو الفخ الذي أنتج «111 مجلدًا بلا معرّف» وهي نتيجة كاذبة.)
- S1 = يفشل رمز الخروج. S2 = تحذير لا يوقف.

الاستخدام
---------
    python scripts/validate_all.py            # تقرير عربي
    python scripts/validate_all.py --json     # مخرَج آلي
    python scripts/validate_all.py --quiet    # سطر واحد (للاستدعاء من الأنابيب)
    python scripts/validate_all.py --write-baseline   # يُعيد ضبط خط أساس الموضوعات
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "meta" / "catalog.yaml"
BASELINE = ROOT / "meta" / "toc_baseline.json"
HASH_FILE = ROOT / "meta" / "output.hash"
HASH_SOURCES = ("output", "index")
BOOKS_META = ROOT / "meta" / "books"
SKILLS = ROOT / ".agents" / "skills"
OUTPUT_DIR = ROOT / "output"
INDEX_DIR = ROOT / "index"

# سكريبتات تكتب في output/ — لا يجوز أن تعمل على كتاب مفترض بصمت.
SILENT_DEFAULT_SCRIPTS = (
    "scripts/convert/run_vision_batch.py",
    "scripts/review/review_batch.py",
)

# مسارات تُذكر كنماذج لا كملفات حقيقية: تُستثنى من فحص الوجود.
PLACEHOLDER = re.compile(r"[$<>{}*…]")
# مسارات طبقة البيانات المحلية: لا تُفحص في CI (غير مرفوعة إلى المستودع).
DATA_PREFIXES = ("output/", "index/", "curriculum_raw/", "curriculum/", "plans/", "logs/")
PATH_REF = re.compile(
    r"(?:scripts|meta|curriculum_raw|curriculum|output|index|logs|plans)[\\/]"
    r"[^\s`\"'()\[\]،,؛;<>|*]+"
)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- أدوات
def result(check: str, severity: str, status: str, summary: str, details=None) -> dict:
    return {
        "id": check,
        "severity": severity,
        "status": status,
        "summary": summary,
        "details": details or [],
    }


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def parse_catalog() -> list[dict]:
    """يحلّل catalog.yaml سطريًا (بلا تبعية pyyaml) ويستخرج الحقول التي نفحصها."""
    txt = CATALOG.read_text(encoding="utf-8-sig")
    books: list[dict] = []
    for chunk in re.split(r"\n  - id: ", txt)[1:]:
        bid = chunk.split("\n", 1)[0].strip()

        def field(name: str) -> str | None:
            m = re.search(rf'^    {name}: "?(.*?)"?\s*$', chunk, re.M)
            return m.group(1) if m else None

        def number(name: str) -> int | None:
            raw = field(name)
            return int(raw) if raw and raw.isdigit() else None

        missing = re.search(r"^    missing_pages: \[(.*?)\]", chunk, re.M)
        missing_list = [int(x) for x in re.findall(r"\d+", missing.group(1))] if missing else []
        offset_raw = field("printed_page_offset")
        books.append(
            {
                "id": bid,
                "text_dir": field("text_dir"),
                "index_dir": field("index_dir"),
                "toc": field("toc"),
                "pages_total": number("pages_total"),
                "pages_converted": number("pages_converted"),
                "printed_page_offset": offset_raw,
                "missing_pages": missing_list,
                "external": "external_sources" in chunk,
            }
        )
    return books


def count_pages(book_dir: Path) -> set[int]:
    pages = set()
    for p in book_dir.glob("page_*.md"):
        m = re.search(r"(\d+)", p.stem)
        if m:
            pages.add(int(m.group(1)))
    return pages


def count_toc(toc_path: Path) -> tuple[int, int]:
    """يعيد (عدد الفصول، عدد الموضوعات) — نفس نمط toc_review.py."""
    chapters = topics = 0
    for line in toc_path.read_text(encoding="utf-8-sig").splitlines():
        if re.match(r'^  - title: "', line):
            chapters += 1
        elif re.match(r'^      - \{ title: "', line):
            topics += 1
    return chapters, topics


# --------------------------------------------------------------------------- الفحوصات
def check_env_hygiene() -> dict:
    env = ROOT / ".env"
    if not env.exists():
        return result("env_hygiene", "S1", "skip", "لا ملف .env — لا سرّ يُحمى")

    details = []
    if not (ROOT / ".gitignore").exists():
        return result("env_hygiene", "S1", "fail", ".env موجود بلا .gitignore")

    inside = git("rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0:
        return result(
            "env_hygiene", "S1", "fail",
            ".env موجود ولا مستودع git يحميه بحظر (أول git init قد يبتلعه)",
        )

    if git("check-ignore", "-q", ".env").returncode != 0:
        details.append(".env غير مستثنى في .gitignore")
    if git("ls-files", "--error-unmatch", ".env").returncode == 0:
        details.append("‏.env متتبَّع داخل المستودع — أزِله من التتبّع فورًا")

    if details:
        return result("env_hygiene", "S1", "fail", "تسريب محتمل لمفتاح .env", details)
    return result("env_hygiene", "S1", "ok", ".env مستثنى وغير متتبَّع")


def check_doc_paths(ci: bool = False) -> dict:
    docs = [ROOT / "AGENTS.md"] + sorted(SKILLS.glob("*/SKILL.md"))
    dead, refs = [], 0
    for doc in docs:
        if not doc.exists():
            dead.append(f"ملف توثيقي مفقود: {doc.relative_to(ROOT)}")
            continue
        txt = doc.read_text(encoding="utf-8-sig")
        for m in PATH_REF.finditer(txt):
            ref = m.group(0).rstrip(".,:؛،")
            if PLACEHOLDER.search(ref):
                continue
            if ci and ref.startswith(DATA_PREFIXES):
                continue  # في CI لا توجد طبقة البيانات المحلية أصلًا
            refs += 1
            target = ROOT / ref.replace("\\", "/")
            if not target.exists():
                line = txt[: m.start()].count("\n") + 1
                dead.append(f"{doc.relative_to(ROOT)}:{line} ← {ref}")
    if dead:
        return result("doc_paths", "S1", "fail", f"{len(dead)} مسارًا ميتًا في الوثائق", dead)
    return result("doc_paths", "S1", "ok", f"{refs} مسارًا في الوثائق كلها موجود")


def check_skill_frontmatter() -> dict:
    problems = []
    found = 0
    for skill in sorted(SKILLS.glob("*/SKILL.md")):
        found += 1
        txt = skill.read_text(encoding="utf-8-sig")
        lines = txt.splitlines()
        if not lines or lines[0].strip() != "---":
            problems.append(f"{skill.parent.name}: بلا ترويسة YAML")
            continue
        try:
            end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
        except StopIteration:
            problems.append(f"{skill.parent.name}: ترويسة غير مغلقة")
            continue
        head = "\n".join(lines[1:end])
        name = re.search(r"^name:\s*(\S.*)$", head, re.M)
        desc = re.search(r"^description:\s*(\S.*)$", head, re.M)
        if not name or name.group(1).strip().strip("\"'") != skill.parent.name:
            problems.append(f"{skill.parent.name}: name مفقود أو لا يطابق اسم المجلد")
        if not desc or len(desc.group(1).strip().strip("\"'")) < 20:
            problems.append(f"{skill.parent.name}: description مفقود أو غير دالّ")
    if problems:
        return result("skill_frontmatter", "S1", "fail", f"{len(problems)} خللًا في ترويسات المهارات", problems)
    return result("skill_frontmatter", "S1", "ok", f"{found} مهارات بترويسة صحيحة")


def check_no_silent_book_default() -> dict:
    problems = []
    for rel in SILENT_DEFAULT_SCRIPTS:
        path = ROOT / rel
        if not path.exists():
            problems.append(f"{rel}: السكريبت غير موجود")
            continue
        src = path.read_text(encoding="utf-8-sig")
        if re.search(r'add_argument\(\s*"--book"\s*,\s*default=', src):
            problems.append(f"{rel}: --book له افتراضي صامت")
        if not re.search(r'add_argument\(\s*"--book"\s*,\s*required=True', src):
            problems.append(f"{rel}: --book ليس required=True")
        if re.search(r'^BOOK\s*=\s*"[^"]+"', src, re.M):
            problems.append(f"{rel}: BOOK مثبت بقيمة افتراضية على مستوى الوحدة")
    if problems:
        return result("no_silent_book_default", "S1", "fail", "كتاب افتراضي صامت في سكريبتات الكتابة", problems)
    return result("no_silent_book_default", "S1", "ok", "لا كتاب افتراضي: --book إلزامي")


def check_pages_converted(books: list[dict], ci: bool = False) -> dict:
    if ci:
        return result("pages_converted", "S1", "skip", "مُتخطّى في CI: يتطلب output/ المحلي")
    problems, checked = [], 0
    for b in books:
        if not b["text_dir"]:
            continue  # مصدر خارجي (external_sources) بلا مجلد محلي
        book_dir = ROOT / b["text_dir"]
        if not book_dir.is_dir():
            problems.append(f"{b['id']}: مجلد النص غير موجود ({b['text_dir']})")
            continue
        checked += 1
        pages = count_pages(book_dir)
        offset = b["printed_page_offset"]
        if offset is None:
            problems.append(f"{b['id']}: بلا printed_page_offset (عدد مطبوع ← ملف غير معروف)")
        elif offset != "unknown" and not re.fullmatch(r"-?\d+", offset):
            problems.append(f"{b['id']}: printed_page_offset غير صالح ({offset}) — -1|0|رقم|unknown")
        if b["pages_converted"] is not None and len(pages) != b["pages_converted"]:
            problems.append(
                f"{b['id']}: pages_converted={b['pages_converted']} والواقع {len(pages)} ملفًا"
            )
        if b["pages_total"]:
            computed = sorted(set(range(1, b["pages_total"] + 1)) - pages)
            if computed != sorted(b["missing_pages"]):
                problems.append(
                    f"{b['id']}: missing_pages في المرجع {b['missing_pages']} "
                    f"والمحسوب {computed[:8]}{'…' if len(computed) > 8 else ''}"
                )
    if problems:
        return result("pages_converted", "S1", "fail", f"{len(problems)} خللًا في عدّ الصفحات", problems)
    return result("pages_converted", "S1", "ok", f"{checked} كتابًا: العدّ مطابق والفقود مطابق")


def check_topics_baseline(books: list[dict], ci: bool = False) -> dict:
    if ci:
        return result("topics_baseline", "S1", "skip", "مُتخطّى في CI: يعتمد على اكتمال طبقة البيانات")
    if not BASELINE.exists():
        return result(
            "topics_baseline", "S1", "fail",
            "خط الأساس مفقود — شغّل: python scripts/validate_all.py --write-baseline",
        )
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    problems, checked, no_base = [], 0, []
    for b in books:
        if not b["text_dir"]:
            continue
        toc = BOOKS_META / b["id"] / "toc.yaml"
        if not toc.exists():
            problems.append(f"{b['id']}: لا toc.yaml (الكتاب مسجَّل بلا فهرس موضوعات)")
            continue
        chapters, topics = count_toc(toc)
        checked += 1
        base = baseline.get(b["id"])
        if base is None:
            no_base.append(b["id"])
            continue
        if topics < base["topics"]:
            problems.append(f"{b['id']}: موضوعات {topics} < خط الأساس {base['topics']}")
        if chapters < base["chapters"]:
            problems.append(f"{b['id']}: فصول {chapters} < خط الأساس {base['chapters']}")
    if problems:
        return result("topics_baseline", "S1", "fail", f"{len(problems)} انحدارًا في الموضوعات", problems)
    summary = f"{checked} كتابًا: لا انحدار عن خط الأساس"
    if no_base:
        summary += f" (بلا خط أساس: {len(no_base)} — أضِفها بـ--write-baseline)"
    return result("topics_baseline", "S1", "ok", summary)


def declared_name(rel: str | None, root_name: str) -> str | None:
    """يستخرج اسم المجلد من مسار معلن كـ output/X أو index/X/norm.

    لا يُقارن المعرّف اللاتيني (id) باسم المجلد العربي أبدًا.
    """
    if not rel:
        return None
    parts = Path(rel).parts
    if parts and parts[0] == root_name:
        parts = parts[1:]
    return parts[0] if parts else None


def check_orphan_dirs(books: list[dict]) -> dict:
    declared_text = {n for n in (declared_name(b["text_dir"], "output") for b in books) if n}
    declared_index = {n for n in (declared_name(b["index_dir"], "index") for b in books) if n}
    out = {p.name for p in OUTPUT_DIR.iterdir() if p.is_dir()} if OUTPUT_DIR.is_dir() else set()
    idx = {p.name for p in INDEX_DIR.iterdir() if p.is_dir()} if INDEX_DIR.is_dir() else set()
    orphan_out = sorted(out - declared_text)
    orphan_idx = sorted(idx - declared_index)
    if not orphan_out and not orphan_idx:
        return result("orphan_dirs", "S2", "ok", "لا مجلدات بلا اعتماد")
    details = (
        [f"output/: {d}" for d in orphan_out[:6]]
        + [f"index/: {d}" for d in orphan_idx[:6]]
    )
    details.append("القرار المؤجَّل: تسجيل الكتابين في catalog.yaml أو نقلهما خارج output/.")
    return result(
        "orphan_dirs", "S2", "warn",
        f"بلا اعتماد: {len(orphan_out)} في output/ و{len(orphan_idx)} في index/",
        details,
    )


# --------------------------------------------------------------------------- بصمة المصادر
def file_digest(path: Path) -> bytes:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.digest()


def tree_digest(root: Path) -> dict:
    """بصمة مجمّعة لكل شجرة: اسم المسار + بصمة المحتوى، بترتيب ثابت."""
    h = hashlib.sha256()
    files = total = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file() or ".cache" in p.parts:
            continue
        h.update(p.relative_to(root).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(file_digest(p))
        files += 1
        total += p.stat().st_size
    return {"files": files, "bytes": total, "digest": h.hexdigest()}


def compute_hash() -> dict:
    sources = {}
    for name in HASH_SOURCES:
        path = ROOT / name
        if path.is_dir():
            sources[name] = tree_digest(path)
    return {
        "version": 1,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "created_epoch": time.time(),
        "sources": sources,
    }


def write_hash() -> int:
    data = compute_hash()
    if not data["sources"]:
        print("[!] لا مجلدات بيانات محلية (output/ أو index/) — لم تُكتب بصمة")
        return 1
    HASH_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"[i] كُتبت البصمة: {HASH_FILE.relative_to(ROOT)}")
    for name, info in data["sources"].items():
        print(f"    {name}: {info['files']} ملفًا / {info['bytes']} بايت / {info['digest'][:16]}…")
    return 0


def newer_files(name: str, since: float, limit: int = 20) -> list[str]:
    """أسماء الملفات التي تغيّرت بعد لحظة البصمة — لتحديد الخلل لا مجرد كشفه."""
    root = ROOT / name
    if not root.is_dir():
        return []
    out: list[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        try:
            if p.stat().st_mtime > since - 1:
                out.append(p.relative_to(ROOT).as_posix())
        except OSError:
            continue
        if len(out) > limit:
            break
    return out


def check_source_hash(ci: bool = False) -> dict:
    present = [n for n in HASH_SOURCES if (ROOT / n).is_dir()]
    if ci or not present:
        return result("source_hash", "S1", "skip", "مُتخطّى: لا طبقة بيانات محلية")
    if not HASH_FILE.exists():
        return result(
            "source_hash", "S1", "fail",
            "البصمة مفقودة — شغّل: python scripts/validate_all.py --write-hash",
        )
    try:
        saved = json.loads(HASH_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return result("source_hash", "S1", "fail", f"ملف البصمة تالف ({exc})")

    problems: list[str] = []
    details: list[str] = []
    for name, old in saved.get("sources", {}).items():
        if not (ROOT / name).is_dir():
            problems.append(f"{name}/: المجلد مفقود كليًا")
            continue
        new = tree_digest(ROOT / name)
        if new["digest"] != old.get("digest") or new["files"] != old.get("files"):
            problems.append(f"{name}/: متوقع {old.get('files')} ملفًا، والواقع {new['files']}")
            details += newer_files(name, float(saved.get("created_epoch", 0)))
    for name in present:
        if name not in saved.get("sources", {}):
            problems.append(f"{name}/: ظهر بعد أخذ البصمة")

    if problems:
        return result(
            "source_hash", "S1", "fail",
            f"{len(problems)} شجرة بيانات تغيّرت بلا تصريح",
            problems + details,
        )
    return result("source_hash", "S1", "ok", "بصمة output/ و index/ مطابقة")


# --------------------------------------------------------------------------- التشغيل
def write_baseline(books: list[dict]) -> int:
    data = {}
    for b in books:
        toc = BOOKS_META / b["id"] / "toc.yaml"
        if b["text_dir"] and toc.exists():
            chapters, topics = count_toc(toc)
            data[b["id"]] = {"chapters": chapters, "topics": topics}
    BASELINE.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[i] كُتب خط الأساس: {BASELINE.relative_to(ROOT)} ({len(data)} كتابًا)")
    return 0


def run(json_out: bool = False, quiet: bool = False, ci: bool = False, hash_check: bool = False) -> int:
    books = parse_catalog()
    checks = [
        check_env_hygiene(),
        check_doc_paths(ci=ci),
        check_skill_frontmatter(),
        check_no_silent_book_default(),
        check_pages_converted(books, ci=ci),
        check_topics_baseline(books, ci=ci),
        check_orphan_dirs(books),
    ]
    if hash_check:
        checks.append(check_source_hash(ci=ci))
    s1 = [c for c in checks if c["severity"] == "S1" and c["status"] == "fail"]
    s2 = [c for c in checks if c["severity"] == "S2" and c["status"] == "warn"]
    ok = not s1

    if json_out:
        print(json.dumps(
            {"ok": ok, "root": str(ROOT), "s1_failures": len(s1), "s2_warnings": len(s2), "checks": checks},
            ensure_ascii=False, indent=2,
        ))
        return 0 if ok else 1

    if quiet:
        mark = "سليم" if ok else f"{len(s1)} مشكلة"
        print(f"[حارس] {mark}" + (f" | {len(s2)} تحذير" if s2 else ""))
        return 0 if ok else 1

    for c in checks:
        icon = {"ok": "[✓]", "fail": "[✗]", "warn": "[!]", "skip": "[-]"}[c["status"]]
        print(f"{icon} {c['summary']}")
        for line in c["details"][:10]:
            print(f"      - {line}")
    print("-" * 60)
    if ok:
        print(f"النتيجة: سليم" + (f" | {len(s2)} تحذيرًا (S2)" if s2 else ""))
    else:
        print(f"النتيجة: {len(s1)} مشكلة مانعة (S1)" + (f" | {len(s2)} تحذيرًا (S2)" if s2 else ""))
    return 0 if ok else 1


def hash_only(quiet: bool = False) -> int:
    """نداء مخصّص لخطاف pre-commit: يحرس البصمة وحدها (سريع، لا يتأثر بدَين البيانات)."""
    c = check_source_hash()
    if c["status"] == "skip":
        print("[بصمة] لا طبقة بيانات محلية — تخطٍ")
        return 0
    if c["status"] == "ok":
        if not quiet:
            print(f"[✓] {c['summary']}")
        return 0
    print(f"[✗] {c['summary']}")
    for line in c["details"][:20]:
        print(f"    - {line}")
    print("[i] إن كان التغيير معتمدًا: python scripts/validate_all.py --write-hash")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="حارس مساحة العمل: ثماني قواعد في نداء واحد")
    parser.add_argument("--json", action="store_true", help="مخرَج JSON آلي")
    parser.add_argument("--quiet", action="store_true", help="سطر واحد فقط")
    parser.add_argument("--write-baseline", action="store_true", help="إعادة ضبط خط أساس الموضوعات")
    parser.add_argument("--write-hash", action="store_true", help="حفظ بصمة output/ و index/ في meta/output.hash")
    parser.add_argument("--check-hash", action="store_true", help="مقارنة البصمة المحفوظة بالواقع")
    parser.add_argument("--hash-only", action="store_true", help="فحص البصمة وحده (لخطاف pre-commit)")
    parser.add_argument("--ci", action="store_true", help="وضع CI: يتخطى ما يحتاج طبقة البيانات المحلية")
    args = parser.parse_args()
    if args.write_baseline:
        return write_baseline(parse_catalog())
    if args.write_hash:
        return write_hash()
    if args.hash_only:
        return hash_only(quiet=args.quiet)
    return run(json_out=args.json, quiet=args.quiet, ci=args.ci, hash_check=args.check_hash)


if __name__ == "__main__":
    sys.exit(main())
