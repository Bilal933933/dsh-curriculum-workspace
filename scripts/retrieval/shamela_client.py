#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shamela_client.py — عميل MCP للاتصال بسيرفر المكتبة الشاملة.

الغرض:
    يوفّر قناة اتصال نصية (CLI) بسيرفر الشاملة الرسمي عبر بروتوكول MCP فوق
    HTTP، حتى يستدعيه أي هارنس (Qoder أو غيره) بأمر سطر أوامر واحد.
    السيرفر يُجري مصافحة MCP ويعمل بمكتبات الإنترنت المعيارية فقط، فلا حاجة
    إلى تثبيت حزمة `mcp` أو بيئة افتراضية إضافية.

ما يقرأه:
    لا يقرأ أي ملف من المنهج. الوسائط كلها من arguments السطر.

ما يكتبه:
    cache/shamela/<UTC>_<أداة>_<وسم>.json   (نسخة من ردّ السيرفر للتوثيق)
    لا يلمس curriculum_raw/ ولا output/ ولا index/ إطلاقًا.

الأدوات المتاحة على السيرفر (v8.1.0):
    shamela_find         بحث عام (keywords + difficulty + قيود مؤلف/كتاب/قسم)
    shamela_find_scoped  بحث مقيّد بعد نتائج أولى (book_ids/author_ids/...)
    shamela_open         فتح صفحة واحدة (book_id + page_id)
    shamela_open_many    فتح عدة صفحات دفعة واحدة مع سياق مجاور

الاستخدام:
    python scripts/retrieval/shamela_client.py tools
    python scripts/retrieval/shamela_client.py find "الاستعارة المكنية" \
        "تشبيه بليغ حذف وجه الشبه" --difficulty medium
    python scripts/retrieval/shamela_client.py find "حذف أدوات الربط" \
        --book "الإتقان" --author "السيوطي"
    python scripts/retrieval/shamela_client.py open 1234 5678 --max-chars 6000
    python scripts/retrieval/shamela_client.py open-many 1234:5678 1234:5679 --context 1

    # مخرجات خام (JSON كامل بلا تلخيص) أو بلا كتابة في الـ cache:
    ... --raw
    ... --no-cache

تنبيه منهجي:
    هذا المرجع طبقة ثالثة في AGENTS.md (§5). لا يُستدعى إلا بعد استنفاد
    المنهج المدرسي (output/ + index/) والسماح بجدول التصعيد في
    .agents/skills/curriculum-retrieval/SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE = Path(__file__).resolve().parents[2]
CACHE_DIR = WORKSPACE / "cache" / "shamela"

MCP_URL = "https://mcp.shamela.ws/"
PROTOCOL_VERSION = "2025-06-18"
CLIENT_NAME = "workspace-shamela-client"
TIMEOUT_SECONDS = 60


class ShamelaError(RuntimeError):
    """خطأ في مصافحة أو استدعاء MCP."""


def _parse_body(raw: bytes, content_type: str) -> dict:
    """قبول ردّ JSON العادي أو تدفّق SSE (`data: {...}`) كما ينص بروتوكول MCP."""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        raise ShamelaError("ردّ فارغ من السيرفر")
    if "text/event-stream" in content_type:
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload:
                    return json.loads(payload)
        raise ShamelaError("تدفّق SSE بلا أي حمولة data:")
    return json.loads(text)


def _rpc(method: str, params: dict, session_id: str | None = None) -> tuple[dict, str | None]:
    """إرسال طلب JSON-RPC واحد وإرجاع (الحمولة، معرّف الجلسة إن وُجد)."""
    request = urllib.request.Request(
        MCP_URL,
        data=json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            **({"mcp-session-id": session_id} if session_id else {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = _parse_body(response.read(), response.headers.get("Content-Type", ""))
            returned_session = response.headers.get("mcp-session-id")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise ShamelaError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ShamelaError(f"تعذّر الوصول إلى {MCP_URL}: {exc.reason}") from exc

    if "error" in payload:
        err = payload["error"]
        raise ShamelaError(f"خطأ MCP {err.get('code')}: {err.get('message')}")
    return payload["result"], returned_session


def _notify(method: str, session_id: str | None) -> None:
    """إشعار MCP (بلا معرّف طلب): السيرفر لا يُلزم بردّ، وأي خطأ فيه غير ملزم."""
    request = urllib.request.Request(
        MCP_URL,
        data=json.dumps({"jsonrpc": "2.0", "method": method, "params": {}}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            **({"mcp-session-id": session_id} if session_id else {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):
            pass
    except (urllib.error.URLError, OSError):
        pass


class ShamelaClient:
    """عميل MCP Minimal: مصافحة واحدة ثم استدعاء أدوات."""

    def __init__(self) -> None:
        self.session_id: str | None = None
        self.server_info: dict = {}

    def connect(self) -> None:
        result, session_id = _rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": "1.0"},
            },
        )
        self.session_id = session_id
        self.server_info = result.get("serverInfo", {})
        _notify("notifications/initialized", self.session_id)

    def list_tools(self) -> list[dict]:
        if not self.session_id:
            self.connect()
        result, _ = _rpc("tools/list", {}, self.session_id)
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> dict:
        if not self.session_id:
            self.connect()
        result, _ = _rpc(
            "tools/call", {"name": name, "arguments": arguments}, self.session_id
        )
        if result.get("isError"):
            raise ShamelaError(f"أداة {name} أرجعت خطأ: {_content_text(result)[:500]}")
        payload = _content_json(result)
        return {"tool": name, "arguments": arguments, "result": payload}


def _content_text(result: dict) -> str:
    return "\n".join(
        item.get("text", "")
        for item in result.get("content", [])
        if item.get("type") == "text"
    )


def _content_json(result: dict):
    """حمولة الأداة نصٌّ JSON في العادة؛ نرجعه مسرّدًا إن أمكن وإلا كنصّ خام."""
    text = _content_text(result)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text if text else result


def _slug(text: str) -> str:
    slug = re.sub(r"[^\w\u0600-\u06FF-]+", "_", text.strip())[:48]
    return slug.strip("_") or "query"


def _write_cache(invocation: dict, query_hint: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = CACHE_DIR / f"{stamp}_{invocation['tool']}_{_slug(query_hint)}.json"
    path.write_text(
        json.dumps(invocation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def _book_index(data: dict) -> dict:
    """خرط book_id → {title, author} من طبقات نتائج البحث."""
    index = {}
    for layer in data.get("layers", []):
        for book in layer.get("results", []):
            if isinstance(book, dict) and book.get("book_id"):
                index.setdefault(book["book_id"], book)
    return index


def _print_human(invocation: dict) -> None:
    """عرض مختصر: المواضع مع الاستشهاد الجاهز، ثم الكتب غير المفتوحة."""
    data = invocation["result"]
    if not isinstance(data, dict):
        print(data)
        return

    books = _book_index(data)
    if "text" in data and "citation" in data:
        print((data["citation"] or {}).get("markdown", ""))
        print((data.get("text") or "").strip()[:4000])
        nav = data.get("navigation") or {}
        print(f"\n[page_id={data.get('page_id')} "
              f"سابق={nav.get('previous_page_id')} لاحق={nav.get('next_page_id')}]")
    sources = (data.get("evidence") or {}).get("sources") or data.get("sources") or []
    if sources:
        print(f"== مواضع مفتوحة ({len(sources)}) ==")
        for src in sources:
            meta = books.get(src.get("book_id"), {})
            cite = (src.get("citation") or {}).get("markdown", "")
            match = re.match(r"\[(.+?)\s*[\(٠-٩ص]", cite)
            title = meta.get("title") or (match.group(1) if match else "؟")
            author = meta.get("author", "؟")
            text = (src.get("text") or "").strip()
            print(f"\n— {title} / {author} / {cite}")
            if text:
                print(text[:700])
            nav = src.get("navigation") or {}
            if nav:
                print(f"  [page_id={src.get('page_id')} "
                      f"سابق={nav.get('previous_page_id')} لاحق={nav.get('next_page_id')}]")

    unopened = [b for b in books.values() if not b.get("opened")]
    if unopened:
        print(f"\n== كتب مرشَّحة بلا فتح ({len(unopened)}) ==")
        for b in unopened[:15]:
            print(f"— {b.get('title', '؟')} | {b.get('author', '؟')} | book_id={b.get('book_id')}")

    for res in data.get("book_resolution", []) + data.get("author_resolution", []):
        print(f"\n[تحقيق القيود] «{res.get('query')}» → {res.get('status')}: "
              f"{', '.join(res.get('matches', [])) or 'لا مطابقة'}")

    if data.get("next_cursor"):
        print(f"\n[!] نتائج أكثر — تابع بـ: --cursor {data['next_cursor']}")

    if not sources and not unopened and "text" not in data:
        print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])


def _drop_empty(args: dict) -> dict:
    """السيرفر يرفض بعض الوسائط المتعارضة (query مع queries)؛ يسقط الفراغ فقط."""
    cleaned = {}
    for key, value in args.items():
        if value is None:
            continue
        if isinstance(value, (list, dict, str)) and not value:
            continue
        cleaned[key] = value
    return cleaned


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="عميل MCP لسيرفر المكتبة الشاملة (بلا اعتماديات خارجية).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("tools", help="عرض أدوات السيرفر المتاحة")

    p_find = sub.add_parser("find", help="بحث عام (shamela_find)")
    p_find.add_argument("keywords", nargs="+", help="عبارات عربية قصيرة، عبارة لكل عنصر")
    p_find.add_argument("--difficulty", choices=["easy", "medium", "hard"], default="easy")
    p_find.add_argument("--field", choices=["body", "footnotes"], default="body")
    p_find.add_argument("--book", action="append", default=[], help="اسم/جزء اسم كتاب مذكور صراحة")
    p_find.add_argument("--author", action="append", default=[], help="اسم/جزء اسم مؤلف مذكور صراحة")
    p_find.add_argument("--category", type=int, action="append", default=[], help="معرّف قسم")
    p_find.add_argument("--cursor", help="متابعة صفحة نتائج سابقة")

    p_scope = sub.add_parser("find-scoped", help="بحث مقيّد (shamela_find_scoped)")
    p_scope.add_argument("--query", help="عبارة واحدة مركّزة")
    p_scope.add_argument("--queries", nargs="*", default=[], help="عدة عبارات داخل نفس النطاق")
    p_scope.add_argument("--book-id", type=int, action="append", default=[])
    p_scope.add_argument("--author-id", type=int, action="append", default=[])
    p_scope.add_argument("--book-name", action="append", default=[])
    p_scope.add_argument("--author-name", action="append", default=[])
    p_scope.add_argument("--category", type=int, action="append", default=[])
    p_scope.add_argument("--exclude", action="append", default=[])
    p_scope.add_argument("--difficulty", choices=["easy", "medium", "hard"], default="easy")
    p_scope.add_argument("--field", choices=["body", "footnotes"], default="body")
    p_scope.add_argument("--limit", type=int, default=10)
    p_scope.add_argument("--cursor")

    p_open = sub.add_parser("open", help="فتح صفحة (shamela_open)")
    p_open.add_argument("book_id", type=int)
    p_open.add_argument("page_id", type=int)
    p_open.add_argument("--max-chars", type=int, default=10000, help="حدّ السيرفر الأدنى 500")
    p_open.add_argument("--field", choices=["body", "footnotes"], default="body")
    p_open.add_argument("--cursor")

    p_many = sub.add_parser("open-many", help="فتح عدة صفحات (shamela_open_many)")
    p_many.add_argument("pages", nargs="+", help="بصيغة book_id:page_id")
    p_many.add_argument("--context", type=int, default=0, help="صفحات مجاورة لكل صفحة (0-3)")
    p_many.add_argument("--max-total-chars", type=int, default=24000)

    for sp in sub.choices.values():
        sp.add_argument("--raw", action="store_true", help="طباعة JSON الكامل كما جاء")
        sp.add_argument("--no-cache", action="store_true", help="لا يكتب في cache/shamela/")
    return parser


def arguments_for(ns: argparse.Namespace) -> tuple[str, dict]:
    if ns.command == "tools":
        return "tools/list", {}
    if ns.command == "find":
        return "shamela_find", {
            "keywords": ns.keywords,
            "difficulty": ns.difficulty,
            "field": ns.field,
            "book_queries": ns.book,
            "author_queries": ns.author,
            "category_ids": ns.category,
            "cursor": ns.cursor,
        }
    if ns.command == "find-scoped":
        if not ns.query and not ns.queries:
            raise ShamelaError("استخدم --query أو --queries")
        return "shamela_find_scoped", {
            "query": ns.query,
            "queries": ns.queries,
            "book_ids": ns.book_id,
            "author_ids": ns.author_id,
            "book_names": ns.book_name,
            "author_names": ns.author_name,
            "category_ids": ns.category,
            "exclude_phrases": ns.exclude,
            "difficulty": ns.difficulty,
            "field": ns.field,
            "limit": ns.limit,
            "cursor": ns.cursor,
        }
    if ns.command == "open":
        return "shamela_open", {
            "book_id": ns.book_id,
            "page_id": ns.page_id,
            "max_chars": ns.max_chars,
            "field": ns.field,
            "cursor": ns.cursor,
        }
    if ns.command == "open-many":
        pages = []
        for token in ns.pages:
            book, _, page = token.partition(":")
            if not page:
                raise ShamelaError(f"صيغة غير صحيحة: {token} — المطلوب book_id:page_id")
            pages.append({"book_id": int(book), "page_id": int(page)})
        return "shamela_open_many", {
            "pages": pages,
            "context": ns.context,
            "max_total_chars": ns.max_total_chars,
        }
    raise ShamelaError(f"أمر غير معروف: {ns.command}")


def main(argv: list[str]) -> int:
    ns = build_parser().parse_args(argv)
    client = ShamelaClient()
    try:
        tool_name, args = arguments_for(ns)
        if tool_name == "tools/list":
            tools = client.list_tools()
            print(f"سيرفر: {client.server_info.get('title', 'shamela')} "
                  f"v{client.server_info.get('version', '?')}")
            for t in tools:
                required = ",".join(t["inputSchema"].get("required", [])) or "-"
                print(f"\n* {t['name']}  (حقول إلزامية: {required})")
                print("  " + (t["description"].split(". ")[0][:220]))
            return 0

        invocation = client.call_tool(tool_name, _drop_empty(args))
        hint = " ".join(map(str, ns.keywords if ns.command == "find" else args.values()))
        if not ns.no_cache:
            path = _write_cache(invocation, hint)
            print(f"[cache] {path.relative_to(WORKSPACE).as_posix()}")
        if ns.raw:
            print(json.dumps(invocation["result"], ensure_ascii=False, indent=2))
        else:
            _print_human(invocation)
        return 0
    except ShamelaError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
