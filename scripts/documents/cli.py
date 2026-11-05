"""واجهة الأوامر لطبقة المستندات.

وظيفة هذا الملف: تحويل كلام سطر الأوامر إلى نداءات على report_task،
ثم طباعة نتيجة واضحة للمستخدم.

الأوامر:
    build  : Markdown  → HTML
    print  : HTML      → PDF
    make   : الخطوتان معًا
    check  : فحص أن مجلد البحث جاهز

الاستخدام:
    python scripts/documents/cli.py make --slug نموذج_التنوين --author "فلان"
"""

from __future__ import annotations

import argparse
import sys

import config
import pdf_print
import report_task


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--slug", required=True, help="اسم مجلد البحث داخل البحوث/")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="توليد مستندات PDF من ملفات Markdown",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="تحويل Markdown إلى HTML")
    _add_common(p_build)
    _add_cover_options(p_build)

    p_print = sub.add_parser("print", help="طبع HTML إلى PDF")
    _add_common(p_print)
    _add_variant(p_print)

    p_make = sub.add_parser("make", help="بناء وطبع معًا")
    _add_common(p_make)
    _add_cover_options(p_make)

    p_check = sub.add_parser("check", help="فحص جاهزية مجلد البحث")
    _add_common(p_check)
    _add_variant(p_check)

    p_serve = sub.add_parser("serve", help="خدمة مجلد البحث على الشبكة للقراءة من الهاتف")
    _add_common(p_serve)
    p_serve.add_argument("--port", type=int, default=config.SERVE_PORT,
                         help=f"منفذ الخدمة (افتراضيًا {config.SERVE_PORT})")

    return parser


def _add_variant(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--variant", default=config.DEFAULT_VARIANT,
                        choices=sorted(config.VARIANTS),
                        help="النسخة: full (مفصّل) أو brief (موجز)")


def _add_cover_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", default=None, help="عنوان الغلاف")
    parser.add_argument("--subtitle", default="", help="عنوان فرعي")
    parser.add_argument("--author", default="", help="اسم المعدّ")
    parser.add_argument("--kicker", default=None, help="نص أعلى الغلاف")
    parser.add_argument("--date", dest="day", default=None, help="التاريخ YYYY-MM-DD")
    _add_variant(parser)


def serve(slug: str, port: int) -> int:
    """يخدم مجلد البحث على كل واجهات الشبكة حتى قراءة الهاتف."""
    import functools
    import http.server

    folder = report_task.report_folder(slug)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(folder))
    with http.server.ThreadingHTTPServer(("0.0.0.0", port), handler) as server:
        print(f"[خدمة] {folder}")
        print(f"[رابط] http://<عنوان-جهازك>:{port}/report.html")
        print("[إيقاف] Ctrl+C")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n[تم] أُوقفت الخدمة")
    return 0


def _cover_options(args: argparse.Namespace) -> dict:
    return {
        "variant": args.variant,
        "title": args.title,
        "subtitle": args.subtitle,
        "author": args.author,
        "kicker": args.kicker,
        "day": args.day,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.command == "serve":
            return serve(args.slug, args.port)

        if args.command == "build":
            path = report_task.build_html(args.slug, **_cover_options(args))
            print(f"[بناء] {path}")

        elif args.command == "print":
            path = report_task.print_pdf(args.slug, args.variant)
            print(f"[طبع] {path}  ({pdf_print.count_pages(path)} صفحة تقريبًا)")

        elif args.command == "make":
            html_path, pdf_path = report_task.make(args.slug, **_cover_options(args))
            size_kb = pdf_path.stat().st_size / 1024
            print(f"[بناء] {html_path}")
            print(f"[طبع] {pdf_path}  ({pdf_print.count_pages(pdf_path)} صفحة، {size_kb:.0f} KB)")

        elif args.command == "check":
            names = report_task.variant_names(args.variant)
            folder = report_task.report_folder(args.slug)
            source = folder / names["source"]
            print(f"[مجلد] {folder}")
            print(f"[النسخة] {args.variant} → {names['source']}")
            print(f"[المصدر] {'موجود' if source.is_file() else 'مفقود: ' + names['source']}")
            print(f"[المتصفح] {pdf_print.find_browser()}")

    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"[خطأ] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
