"""معاينة بصرية لمستند PDF: تحويل صفحاته إلى صور PNG للمراجعة.

وظيفة هذا الملف: العرض والفحص فقط — لا يبني ولا يطبع ولا يقرأ Markdown.
يُستخدم للتحقق من التنسيق العربي (RTL) والفهرس والجداول قبل التسليم.

الاستخدام:
    python scripts/documents/preview.py --slug نموذج_التنوين
    python scripts/documents/preview.py --slug نموذج_التنوين --pages 1,2,3 --dpi 110

المتطلب: pypdfium2 (في requirements.txt، للعرض فقط).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import config


def preview_dir(folder: Path) -> Path:
    """يعيد مجلد المعاينة داخل مجلد البحث، وينشئه إن لزم."""
    out = folder / config.PREVIEW_DIR_NAME
    out.mkdir(parents=True, exist_ok=True)
    return out


def parse_pages(spec: str | None, total: int) -> list[int]:
    """يحوّل «1,2,5» أو «all» إلى قائمة أرقام صفحات (تبدأ من 1)."""
    if not spec or spec.strip().lower() == "all":
        return list(range(1, total + 1))
    numbers: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        page = int(part)
        if 1 <= page <= total:
            numbers.append(page)
    return numbers


def pages_to_png(pdf_path: Path, out_dir: Path,
                 pages: list[int] | None = None,
                 dpi: int = 110) -> list[Path]:
    """يصدّر الصفحات المطلوبة صورًا PNG ويعيد مساراتها."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "مكتبة المعاينة غير مثبتة. ثبّتها داخل البيئة:\n"
            r"  scripts\.venv\Scripts\python.exe -m pip install pypdfium2"
        ) from exc

    document = pdfium.PdfDocument(str(pdf_path))
    total = len(document)
    targets = pages or list(range(1, total + 1))

    width_px = 0
    results: list[Path] = []
    scale = dpi / 72

    for number in targets:
        page = document[number - 1]
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        out = out_dir / f"page_{number:02d}.png"
        image.save(out, "PNG")
        width_px = max(width_px, image.width)
        results.append(out)

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="معاينة صفحات PDF كصور PNG")
    parser.add_argument("--slug", required=True, help="اسم مجلد البحث داخل البحوث/")
    parser.add_argument("--pages", default=None, help="أرقام الصفحات مثل 1,2,3 أو all")
    parser.add_argument("--dpi", type=int, default=config.PREVIEW_DPI, help="دقة العرض")
    args = parser.parse_args(argv)

    folder = config.DOCS_DIR / args.slug
    pdf_path = folder / config.PDF_NAME
    if not pdf_path.is_file():
        print(f"[خطأ] لا يوجد {config.PDF_NAME}: {pdf_path}", file=sys.stderr)
        return 1

    try:
        out_dir = preview_dir(folder)
        targets = parse_pages(args.pages, 999)
        produced = pages_to_png(pdf_path, out_dir, targets, dpi=args.dpi)
    except (RuntimeError, OSError) as exc:
        print(f"[خطأ] {exc}", file=sys.stderr)
        return 1

    print(f"[معاينة] {len(produced)} صورة في: {out_dir}")
    for path in produced:
        print(f"  - {path.name}  ({path.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
