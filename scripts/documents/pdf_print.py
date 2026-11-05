"""طبع ملف HTML إلى PDF عبر متصفح النظام (Chrome / Edge).

وظيفة هذا الملف: الطبع وحده — لا يعرف شيئًا عن Markdown ولا عن القوالب.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import config


def find_browser() -> str:
    """يعيد مسار المتصفح المتاح، أو يرفع خطأً واضحًا."""
    from_env = os.environ.get("CHROME_PATH")
    if from_env and Path(from_env).is_file():
        return from_env

    for candidate in config.BROWSER_CANDIDATES:
        if Path(candidate).is_file():
            return candidate

    on_path = shutil.which("chrome") or shutil.which("msedge")
    if on_path:
        return on_path

    raise FileNotFoundError(
        "لم يُعثر على Chrome أو Edge. حدّد المسار في المتغير CHROME_PATH."
    )


def print_pdf(html_path: Path, pdf_path: Path,
              timeout: int | None = None) -> Path:
    """يطبع HTML إلى PDF ويعيد مسار الناتج."""
    browser = find_browser()
    html_path = html_path.resolve()
    pdf_path = pdf_path.resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists():
        pdf_path.unlink()

    timeout = timeout or config.PRINT_TIMEOUT_SECONDS
    base_flags = [
        *config.REQUIRED_FLAGS,
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        f"--virtual-time-budget={config.VIRTUAL_TIME_BUDGET_MS}",
        f"--print-to-pdf={pdf_path}",
        "--no-pdf-header-footer",
    ]

    profile = config.PROFILE_DIR
    profile.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    for headless_flag in config.HEADLESS_FLAGS:
        command = [browser, headless_flag, f"--user-data-dir={profile}",
                   *base_flags, html_path.as_uri()]
        process = subprocess.run(command, capture_output=True, text=True,
                                 timeout=timeout)

        if pdf_path.is_file() and pdf_path.stat().st_size > config.MIN_PDF_BYTES:
            return pdf_path

        errors.append(f"{headless_flag}: rc={process.returncode} {process.stderr[-400:]}")

    raise RuntimeError("فشل توليد PDF:\n" + "\n".join(errors))


def count_pages(pdf_path: Path) -> int:
    """يعدّ الصفحات تقديرًا بقراءة كائنات الصفحة في الملف."""
    data = pdf_path.read_bytes()
    return data.count(b"/Type /Page") - data.count(b"/Type /Pages")
